from __future__ import annotations

import asyncio
import json
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
from opentelemetry import trace

from yolk.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

tracer = trace.get_tracer(__name__)

RETRY_DELAYS = [1.0, 2.0, 4.0]

MOCK_EVALUATION_JSON = json.dumps(
    {
        "overall_score": 5.8,
        "rubric_results": {
            "asked_about_budget": {
                "question": "Did the rep ask about budget?",
                "answer": False,
                "confidence": 0.92,
                "evidence": "No budget-related questions found in transcript",
            },
            "identified_decision_maker": {
                "question": "Did the rep identify the decision maker?",
                "answer": True,
                "confidence": 0.87,
                "evidence": "Rep asked: 'Who else would be involved in evaluating this?'",
            },
            "asked_timeline": {
                "question": "Did the rep ask about timeline?",
                "answer": False,
                "confidence": 0.95,
                "evidence": "No timeline questions were asked",
            },
            "handled_objections": {
                "question": "Did the rep handle objections effectively?",
                "answer": True,
                "confidence": 0.78,
                "evidence": "Rep acknowledged the concern but pivot was weak",
            },
            "clear_next_steps": {
                "question": "Did the rep establish clear next steps?",
                "answer": False,
                "confidence": 0.91,
                "evidence": "Call ended without defined follow-up",
            },
            "active_listening": {
                "question": "Did the rep demonstrate active listening?",
                "answer": True,
                "confidence": 0.83,
                "evidence": "Rep paraphrased buyer's concerns twice",
            },
        },
        "skill_scores": {
            "discovery": {
                "skill_name": "discovery",
                "category": "qualification",
                "score": 4.0,
                "max_score": 10.0,
                "feedback": (
                    "Missed critical discovery questions about "
                    "budget, timeline, and current pain points"
                ),
            },
            "objection_handling": {
                "skill_name": "objection_handling",
                "category": "negotiation",
                "score": 6.5,
                "max_score": 10.0,
                "feedback": (
                    "Acknowledged objections but failed to reframe value proposition effectively"
                ),
            },
            "negotiation": {
                "skill_name": "negotiation",
                "category": "negotiation",
                "score": 5.0,
                "max_score": 10.0,
                "feedback": "Gave discount too early without getting anything in return",
            },
            "closing": {
                "skill_name": "closing",
                "category": "closing",
                "score": 3.0,
                "max_score": 10.0,
                "feedback": "No close attempt. Ended call without next steps or commitment",
            },
            "rapport_building": {
                "skill_name": "rapport_building",
                "category": "communication",
                "score": 7.5,
                "max_score": 10.0,
                "feedback": "Good opening, built initial trust. Could mirror more.",
            },
            "active_listening": {
                "skill_name": "active_listening",
                "category": "communication",
                "score": 6.0,
                "max_score": 10.0,
                "feedback": (
                    "Paraphrased some points but interrupted buyer twice during critical moments"
                ),
            },
        },
        "strengths": [
            "Strong rapport building — buyer felt comfortable quickly",
            "Good product knowledge when explaining features",
        ],
        "weaknesses": [
            "Missed budget and timeline questions entirely",
            "No closing attempt or defined next steps",
            "Offered discount before buyer even asked — left money on the table",
        ],
        "recommended_scenarios": ["discovery_basics", "closing_momentum", "objection_price"],
    }
)

MOCK_ROLEPLAY_RESPONSES: dict[str, list[str]] = {
    "greeting": [
        (
            "Hi. Yeah, I got your email. Look, I've got about "
            "15 minutes before my next meeting, so let's make "
            "this quick. What exactly does your platform do?"
        ),
        (
            "Hey there. I'll be honest, I wasn't really expecting "
            "this call but your email caught my eye. I'm curious "
            "but skeptical. Pitch me."
        ),
        (
            "Hello. Before you start \u2014 I've seen a dozen demos "
            "this quarter already. What makes yours different? "
            "And please, no buzzwords."
        ),
    ],
    "discovery": [
        (
            "Well, our main challenge is that ramp time for new "
            "reps is about 6 months right now. We lose deals "
            "because junior reps don't know how to handle "
            "objections. But I'm not sure another tool is the "
            "answer \u2014 we tried Gong last year."
        ),
        (
            "Hmm, good question. We're running a team of 40 SDRs "
            "and the conversion rate has been dropping. I think "
            "the issue is discovery calls \u2014 reps aren't asking "
            "the right questions. But how would AI actually fix that?"
        ),
        (
            "Our pipeline is healthy but win rates are down 15% "
            "this quarter. The VP of Sales thinks it's a coaching "
            "problem. Personally, I think it's a hiring problem. "
            "But I'm open to hearing your take."
        ),
    ],
    "qualification": [
        (
            "Budget... I'd say somewhere in the $50K to $80K range "
            "annually, but our CFO will need to sign off on anything "
            "over $30K. Timeline-wise, we're looking at Q2 if we "
            "move forward. We're also talking to two other vendors."
        ),
        (
            "We don't have a hard budget yet \u2014 still in exploration "
            "mode. But if the ROI is clear, I can probably get "
            "$60-100K approved. Decision would be me plus our CRO. "
            "She's the tough one."
        ),
        (
            "I can authorize up to $40K myself. Anything above that "
            "goes to procurement, and that's a 6-week process. So "
            "if you're thinking of closing this month, that's not "
            "realistic."
        ),
    ],
    "objection_handling": [
        (
            "Look, we tried AI coaching before \u2014 spent $80K on a "
            "platform that nobody used after month two. How is this "
            "different? I need more than promises."
        ),
        (
            "Your competitor quoted us 30% less for basically the "
            "same thing. I get that you think you're better, but "
            "from where I'm sitting, features look pretty similar. "
            "Why should I pay more?"
        ),
        (
            "I'm worried about adoption. My team is already drowning "
            "in tools. Salesforce, Outreach, Gong, Slack \u2014 adding "
            "another thing feels like it'll just create more friction."
        ),
    ],
    "negotiation": [
        (
            "Okay, I'm interested. But I need you to work with me "
            "on price. If we commit to an annual contract, can you "
            "do better than list price? And I want the analytics "
            "module included, not as an add-on."
        ),
        (
            "Here's the thing \u2014 I like what I see, but I need to "
            "justify this to the CFO. Can we do a 90-day pilot "
            "with a smaller team first? If the numbers look good, "
            "we'll roll out company-wide."
        ),
        (
            "We're close. But I've got the competing offer at 30% "
            "less sitting on my desk. I want to go with you, but I "
            "need you to sharpen your pencil. What can you do?"
        ),
    ],
    "closing": [
        (
            "Alright, you've addressed most of my concerns. What "
            "does the implementation timeline look like? And walk "
            "me through the contract terms \u2014 I want to understand "
            "the commitment."
        ),
        (
            "I'll be honest, I need to think about this. Can you "
            "send me a summary of what we discussed? I want to run "
            "it by my CRO before making any commitments."
        ),
        (
            "I like it. I think we can move forward. What are the "
            "next steps on your end? I'll need a formal proposal "
            "to take to procurement by Friday."
        ),
    ],
    "wrap_up": [
        (
            "Good conversation. I'm cautiously optimistic. Send me "
            "that proposal and let's set up a call with my CRO next "
            "week. No promises, but you're in the running."
        ),
        (
            "Thanks for your time. Honestly, I'm more interested "
            "than I expected to be. Let me digest everything and "
            "I'll get back to you by Thursday. If I don't, ping "
            "me \u2014 I get busy."
        ),
        (
            "Alright, I think we're done for today. I'll be straight "
            "with you \u2014 you're my top choice right now, but I have "
            "one more demo tomorrow. Send me the pricing breakdown "
            "and let's go from there."
        ),
    ],
}


@dataclass
class LLMMessage:
    role: str
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, Any]


class LLMClient:
    def __init__(self) -> None:
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

    async def close(self) -> None:
        await self._http_client.aclose()

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        model = model or settings.llm_model

        with tracer.start_as_current_span("llm.complete", attributes={"llm.model": model}):
            for attempt, delay in enumerate(RETRY_DELAYS):
                try:
                    return await self._call_provider(
                        messages, model=model, temperature=temperature, max_tokens=max_tokens
                    )
                except (httpx.HTTPStatusError, httpx.TimeoutException):
                    if attempt == len(RETRY_DELAYS) - 1:
                        raise
                    await asyncio.sleep(delay)

            msg = "LLM request failed after all retries"
            raise LLMError(msg)

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        model = model or settings.llm_model

        with tracer.start_as_current_span("llm.stream", attributes={"llm.model": model}):
            if settings.llm_provider == "openai":
                async for chunk in self._stream_openai(
                    messages, model=model, temperature=temperature, max_tokens=max_tokens
                ):
                    yield chunk
            else:
                async for chunk in self._stream_anthropic(
                    messages, model=model, temperature=temperature, max_tokens=max_tokens
                ):
                    yield chunk

    async def _call_provider(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        if settings.llm_provider == "mock":
            return await self._call_mock(messages)
        if settings.llm_provider == "openai":
            return await self._call_openai(
                messages, model=model, temperature=temperature, max_tokens=max_tokens
            )
        return await self._call_anthropic(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )

    async def _call_mock(self, messages: list[LLMMessage]) -> LLMResponse:
        await asyncio.sleep(random.uniform(0.3, 1.2))  # noqa: S311

        is_evaluation = any(
            "evaluator" in m.content.lower() for m in messages if m.role == "system"
        )
        if is_evaluation:
            return LLMResponse(content=MOCK_EVALUATION_JSON, model="mock", usage={})

        phase = "greeting"
        for m in messages:
            if m.role == "system" and "Current phase:" in m.content:
                for p in MOCK_ROLEPLAY_RESPONSES:
                    if p in m.content.lower():
                        phase = p
                        break

        responses = MOCK_ROLEPLAY_RESPONSES.get(phase, MOCK_ROLEPLAY_RESPONSES["greeting"])
        return LLMResponse(
            content=random.choice(responses),  # noqa: S311
            model="mock",
            usage={"prompt_tokens": 150, "completion_tokens": 80},
        )

    async def _stream_mock(self, messages: list[LLMMessage]) -> AsyncIterator[str]:
        response = await self._call_mock(messages)
        words = response.content.split()
        for word in words:
            yield word + " "
            await asyncio.sleep(random.uniform(0.02, 0.08))  # noqa: S311

    async def _call_openai(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        api_key = settings.openai_api_key.get_secret_value()
        base_url = settings.openai_base_url.rstrip("/")
        response = await self._http_client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", model),
            usage=data.get("usage", {}),
        )

    async def _call_anthropic(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        api_key = settings.anthropic_api_key.get_secret_value()
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        body: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg:
            body["system"] = system_msg

        response = await self._http_client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        response.raise_for_status()
        data = response.json()
        return LLMResponse(
            content=data["content"][0]["text"],
            model=data["model"],
            usage=data.get("usage", {}),
        )

    async def _stream_openai(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        api_key = settings.openai_api_key.get_secret_value()
        base_url = settings.openai_base_url.rstrip("/")
        async with self._http_client.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                import json

                chunk = json.loads(line[6:])
                delta = chunk["choices"][0].get("delta", {})
                if content := delta.get("content"):
                    yield content

    async def _stream_anthropic(
        self,
        messages: list[LLMMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        api_key = settings.anthropic_api_key.get_secret_value()
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        body: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system_msg:
            body["system"] = system_msg

        async with self._http_client.stream(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                import json

                event = json.loads(line[6:])
                if event.get("type") == "content_block_delta" and (
                    text := event.get("delta", {}).get("text")
                ):
                    yield text


class LLMError(Exception):
    pass
