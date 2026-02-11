from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from yolk.core.state_machine import ConversationStateMachine, Phase
from yolk.models.session import RoleplayMessage, RoleplaySession
from yolk.services.llm import LLMClient, LLMMessage
from yolk.services.orchestrator import SCENARIO_CATALOG

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

tracer = trace.get_tracer(__name__)


@dataclass
class ActiveSession:
    session_id: uuid.UUID
    user_id: uuid.UUID
    state_machine: ConversationStateMachine
    conversation_history: list[LLMMessage] = field(default_factory=list)
    system_prompt: str = ""


class RoleplayService:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client
        self._active_sessions: dict[uuid.UUID, ActiveSession] = {}

    async def start_session(
        self,
        session_id: uuid.UUID,
        db: AsyncSession,
    ) -> ActiveSession:
        with tracer.start_as_current_span(
            "roleplay.start_session",
            attributes={"session.id": str(session_id)},
        ):
            db_session = await db.get(RoleplaySession, session_id)
            if not db_session:
                msg = f"Session {session_id} not found"
                raise RoleplayError(msg)

            scenario = SCENARIO_CATALOG.get(db_session.scenario_id)
            if not scenario:
                msg = f"Scenario {db_session.scenario_id} not found"
                raise RoleplayError(msg)

            state_machine = ConversationStateMachine()

            system_prompt = self._build_system_prompt(scenario.buyer_persona, scenario.context)

            active = ActiveSession(
                session_id=session_id,
                user_id=db_session.user_id,
                state_machine=state_machine,
                conversation_history=[LLMMessage(role="system", content=system_prompt)],
                system_prompt=system_prompt,
            )

            self._active_sessions[session_id] = active

            db_session.status = "active"
            await db.flush()

            return active

    async def process_message(
        self,
        session_id: uuid.UUID,
        user_message: str,
        db: AsyncSession,
    ) -> str:
        with tracer.start_as_current_span(
            "roleplay.process_message",
            attributes={"session.id": str(session_id)},
        ):
            active = self._active_sessions.get(session_id)
            if not active:
                msg = f"No active session {session_id}"
                raise RoleplayError(msg)

            active.state_machine.record_turn()

            active.conversation_history.append(LLMMessage(role="user", content=user_message))

            phase_instruction = active.state_machine.current_prompt
            suggested = active.state_machine.should_suggest_transition()
            if suggested:
                phase_instruction += (
                    f"\n\n[INTERNAL: Consider naturally transitioning the conversation "
                    f"toward the {suggested.value} phase.]"
                )

            context_message = LLMMessage(
                role="system",
                content=(
                    f"[Current phase: {active.state_machine.current_phase}]\n{phase_instruction}"
                ),
            )

            messages_for_llm = [
                *active.conversation_history[:1],
                context_message,
                *active.conversation_history[1:],
            ]

            response = await self._llm.complete(messages_for_llm, temperature=0.8, max_tokens=512)
            ai_response = response.content

            active.conversation_history.append(LLMMessage(role="assistant", content=ai_response))

            await self._detect_and_apply_transition(active, user_message, ai_response)

            db_session = await db.get(RoleplaySession, session_id)
            if db_session:
                turn = active.state_machine.turn_count

                user_msg = RoleplayMessage(
                    session_id=session_id,
                    role="user",
                    content=user_message,
                    phase=active.state_machine.current_phase,
                    sequence_number=turn * 2 - 1,
                )
                ai_msg = RoleplayMessage(
                    session_id=session_id,
                    role="assistant",
                    content=ai_response,
                    phase=active.state_machine.current_phase,
                    sequence_number=turn * 2,
                )
                db.add(user_msg)
                db.add(ai_msg)

                db_session.turn_count = turn
                db_session.current_phase = active.state_machine.current_phase
                db_session.context = {
                    **db_session.context,
                    "state_machine": active.state_machine.to_dict(),
                }
                await db.flush()

            return ai_response

    async def end_session(
        self,
        session_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict[str, Any]:
        with tracer.start_as_current_span("roleplay.end_session"):
            active = self._active_sessions.pop(session_id, None)

            db_session = await db.get(RoleplaySession, session_id)
            if db_session:
                db_session.status = "completed"
                if active:
                    db_session.evaluation_summary = {
                        "total_turns": active.state_machine.turn_count,
                        "phases_visited": {
                            str(k): v for k, v in active.state_machine.phase_turn_counts.items()
                        },
                        "final_phase": str(active.state_machine.current_phase),
                    }
                await db.flush()

            if db_session and db_session.evaluation_summary is not None:
                return db_session.evaluation_summary
            return {}

    def get_active_session(self, session_id: uuid.UUID) -> ActiveSession | None:
        return self._active_sessions.get(session_id)

    def _build_system_prompt(self, buyer_persona: str, context: str) -> str:
        return (
            f"You are a potential buyer in a sales roleplay training exercise.\n\n"
            f"YOUR PERSONA: {buyer_persona}\n\n"
            f"SITUATION: {context}\n\n"
            f"RULES:\n"
            f"- Stay in character at all times\n"
            f"- React naturally to what the sales rep says\n"
            f"- Don't make it too easy — challenge them appropriately\n"
            f"- If they ask good questions, reward them with useful information\n"
            f"- If they push too hard or miss cues, become more resistant\n"
            f"- Keep responses concise (2-4 sentences typically)\n"
            f"- Never break character or mention this is a simulation"
        )

    async def _detect_and_apply_transition(
        self,
        active: ActiveSession,
        user_message: str,
        ai_response: str,
    ) -> None:
        phase_keywords: dict[Phase, list[str]] = {
            Phase.DISCOVERY: [
                "tell me about",
                "what challenges",
                "how do you currently",
                "walk me through",
            ],
            Phase.QUALIFICATION: ["budget", "timeline", "decision maker", "who else"],
            Phase.OBJECTION_HANDLING: ["concern", "worried", "not sure", "competitor", "expensive"],
            Phase.NEGOTIATION: ["pricing", "discount", "deal", "package", "terms"],
            Phase.CLOSING: ["next steps", "move forward", "sign", "start", "implement"],
            Phase.WRAP_UP: ["thank you", "follow up", "send over", "talk soon"],
        }

        combined = f"{user_message} {ai_response}".lower()
        for target_phase, keywords in phase_keywords.items():
            if target_phase == active.state_machine.current_phase:
                continue
            if not active.state_machine.can_transition_to(target_phase):
                continue
            matches = sum(1 for kw in keywords if kw in combined)
            if matches >= 2:
                await active.state_machine.transition_to(target_phase)
                break


class RoleplayError(Exception):
    pass
