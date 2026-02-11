#!/usr/bin/env python3
"""Interactive roleplay demo with LLM-powered evaluation.

Usage:
    uv run python scripts/demo_roleplay.py
    uv run python scripts/demo_roleplay.py --session <SESSION_ID>
    uv run python scripts/demo_roleplay.py --new --user <USER_ID>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx
import websockets

API_BASE = "http://localhost:8000/api/v1"
WS_BASE = "ws://localhost:8000/api/v1"


async def list_sessions() -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/sessions/")
        resp.raise_for_status()
        return resp.json()


async def auto_assign(user_id: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{API_BASE}/sessions/auto-assign/{user_id}")
        resp.raise_for_status()
        return resp.json()


async def evaluate_session(session_id: str) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(f"{API_BASE}/sessions/{session_id}/evaluate")
        resp.raise_for_status()
        return resp.json()


async def get_messages(session_id: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}/sessions/{session_id}/messages")
        resp.raise_for_status()
        return resp.json()


def print_header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_analysis(result: dict) -> None:
    analysis = result.get("analysis", {})

    print_header("EVALUATION RESULTS")

    print(f"  Scenario:    {result.get('scenario_id', '?')}")
    print(f"  Skills:      {', '.join(result.get('target_skills', []))}")
    print(f"  Turns:       {result.get('turn_count', 0)}")
    print(f"  Score:       {analysis.get('overall_score', '?')}/10")
    print(f"  Engagement:  {analysis.get('buyer_engagement', '?')}/10")
    print(f"  Close deal:  {'Yes' if analysis.get('would_close_deal') else 'No'}")

    if summary := analysis.get("summary"):
        print(f"\n  Summary: {summary}")

    if phases := analysis.get("phase_analysis"):
        print(f"\n{'─' * 60}")
        print("  Phase Analysis:")
        for phase, data in phases.items():
            score = data.get("score", "?")
            feedback = data.get("feedback", "")
            print(f"    [{score}/10] {phase}")
            if feedback:
                for line in _wrap(feedback, 50):
                    print(f"           {line}")

    if strengths := analysis.get("strengths"):
        print("\n  Strengths:")
        for s in strengths:
            print(f"    + {s}")

    if weaknesses := analysis.get("weaknesses"):
        print("\n  Weaknesses:")
        for w in weaknesses:
            print(f"    - {w}")

    if tips := analysis.get("improvement_tips"):
        print("\n  Tips:")
        for i, tip in enumerate(tips, 1):
            print(f"    {i}. {tip}")

    print()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines


async def pick_session() -> str | None:
    sessions = await list_sessions()
    available = [s for s in sessions if s["status"] in ("created", "active")]

    if not available:
        print("No available sessions. Create new ones with --new --user <USER_ID>")
        return None

    print_header("AVAILABLE SESSIONS")
    for i, s in enumerate(available, 1):
        print(
            f"  {i}. [{s['scenario_id']}] "
            f"status={s['status']}, "
            f"skills={', '.join(s['target_skills'])}"
        )
        print(f"     id: {s['id']}")

    print()
    choice = input(f"Pick session (1-{len(available)}) or 'q' to quit: ").strip()
    if choice.lower() == "q":
        return None

    try:
        idx = int(choice) - 1
        return available[idx]["id"]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return None


async def run_roleplay(session_id: str) -> None:
    url = f"{WS_BASE}/ws/roleplay/{session_id}"
    print(f"\n  Connecting to {url}...")

    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            msg = json.loads(await ws.recv())
            if msg["type"] != "session_started":
                print(f"  Unexpected: {msg}")
                return

            print_header(f"ROLEPLAY SESSION — Phase: {msg['phase']}")
            print("  Type your sales pitch. Commands:")
            print("    /quit     — end session & get evaluation")
            print("    /skip     — end session without evaluation")
            print("    /phase    — show current phase")
            print()

            while True:
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, input, "  YOU > "
                    )
                except EOFError:
                    break

                if not user_input.strip():
                    continue

                if user_input.strip() == "/phase":
                    print("  (phase info comes with next AI response)")
                    continue

                if user_input.strip() == "/skip":
                    await ws.send(json.dumps({"type": "end_session"}))
                    end = await _recv_skip_heartbeat(ws)
                    turns = end.get("evaluation_summary", {}).get("total_turns", 0)
                    print(f"\n  Session ended. Total turns: {turns}")
                    return

                if user_input.strip() == "/quit":
                    await ws.send(json.dumps({"type": "end_session"}))
                    end = await _recv_skip_heartbeat(ws)
                    turns = end.get("evaluation_summary", {}).get("total_turns", 0)
                    print(f"\n  Session ended. Total turns: {turns}")

                    print("\n  Running LLM evaluation...")
                    try:
                        result = await evaluate_session(session_id)
                        print_analysis(result)
                    except httpx.HTTPStatusError as e:
                        print(f"  Evaluation failed: {e.response.status_code} {e.response.text}")
                    return

                await ws.send(json.dumps({"type": "message", "content": user_input}))

                resp = await _recv_skip_heartbeat(ws)
                while resp.get("type") == "typing":
                    resp = await _recv_skip_heartbeat(ws)

                if resp.get("type") == "message":
                    phase = resp.get("phase", "?")
                    turn = resp.get("turn_number", "?")
                    content = resp.get("content", "")
                    print(f"  BUYER [{phase} t{turn}] > {content}\n")

                    if resp.get("is_final"):
                        print("  (Buyer ended the conversation)")
                        print("\n  Running LLM evaluation...")
                        try:
                            result = await evaluate_session(session_id)
                            print_analysis(result)
                        except httpx.HTTPStatusError as e:
                            print(
                                f"  Evaluation failed: {e.response.status_code} {e.response.text}"
                            )
                        return

                elif resp.get("type") == "session_ended":
                    print("  Session ended by server.")
                    return
                elif resp.get("type") == "error":
                    print(f"  ERROR: {resp.get('error')}")
                    return

    except websockets.exceptions.ConnectionClosedError as e:
        print(f"\n  Connection closed: {e}")
    except ConnectionRefusedError:
        print("\n  Could not connect. Is the server running? (uv run uvicorn yolk.main:app)")


async def _recv_skip_heartbeat(ws: websockets.ClientConnection) -> dict:
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=120)
        msg = json.loads(raw)
        if msg.get("type") != "heartbeat":
            return msg


async def main() -> None:
    parser = argparse.ArgumentParser(description="YolkDemo interactive roleplay")
    parser.add_argument("--session", "-s", help="Session ID to connect to")
    parser.add_argument("--new", action="store_true", help="Auto-assign new sessions")
    parser.add_argument("--user", "-u", help="User ID (required with --new)")
    parser.add_argument("--evaluate", "-e", help="Evaluate an existing session (no roleplay)")
    parser.add_argument("--transcript", "-t", help="Show transcript for session")
    args = parser.parse_args()

    if args.transcript:
        messages = await get_messages(args.transcript)
        if not messages:
            print("No messages in this session.")
            return
        print_header("SESSION TRANSCRIPT")
        for msg in messages:
            role = "YOU  " if msg["role"] == "user" else "BUYER"
            print(f"  [{msg['phase']}] {role}: {msg['content']}\n")
        return

    if args.evaluate:
        print("  Running LLM evaluation...")
        result = await evaluate_session(args.evaluate)
        print_analysis(result)
        return

    if args.new:
        if not args.user:
            print("--user is required with --new")
            sys.exit(1)
        print(f"  Auto-assigning training for user {args.user}...")
        sessions = await auto_assign(args.user)
        print(f"  Created {len(sessions)} session(s):")
        for s in sessions:
            print(f"    - {s['scenario_id']} → {s['id']}")
        return

    session_id = args.session
    if not session_id:
        session_id = await pick_session()

    if not session_id:
        return

    await run_roleplay(session_id)


if __name__ == "__main__":
    asyncio.run(main())
