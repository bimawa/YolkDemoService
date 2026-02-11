from __future__ import annotations

from typing import Any

import structlog
from faststream.rabbit import RabbitBroker, RabbitQueue

from yolk.config import settings

logger = structlog.get_logger()

broker = RabbitBroker(settings.rabbitmq_url)

call_evaluation_queue = RabbitQueue("call-evaluation", durable=True)
training_assignment_queue = RabbitQueue("training-assignment", durable=True)
notification_queue = RabbitQueue("notifications", durable=True)


@broker.subscriber(call_evaluation_queue)
async def handle_call_evaluation(data: dict[str, Any]) -> None:
    logger.info("processing_call_evaluation", call_id=data.get("call_id"))

    import uuid

    from yolk.api.deps import get_llm_client_instance
    from yolk.database import async_session_factory
    from yolk.services.evaluation import EvaluationService

    call_id = uuid.UUID(data["call_id"])
    llm_client = get_llm_client_instance()
    service = EvaluationService(llm_client)

    async with async_session_factory() as db:
        try:
            evaluation = await service.evaluate_call(call_id, db)
            await db.commit()

            await broker.publish(
                {
                    "user_id": str(data["user_id"]),
                    "evaluation_id": str(evaluation.id),
                },
                queue=training_assignment_queue,
            )

            logger.info(
                "call_evaluation_completed",
                call_id=str(call_id),
                score=evaluation.overall_score,
            )
        except Exception:
            await db.rollback()
            logger.exception("call_evaluation_failed", call_id=str(call_id))
            raise


@broker.subscriber(training_assignment_queue)
async def handle_training_assignment(data: dict[str, Any]) -> None:
    logger.info("processing_training_assignment", user_id=data.get("user_id"))

    import uuid

    from yolk.api.deps import get_llm_client_instance
    from yolk.database import async_session_factory
    from yolk.services.evaluation import EvaluationService
    from yolk.services.orchestrator import GapToGameOrchestrator

    user_id = uuid.UUID(data["user_id"])
    llm_client = get_llm_client_instance()
    eval_service = EvaluationService(llm_client)
    orchestrator = GapToGameOrchestrator(eval_service)

    async with async_session_factory() as db:
        try:
            sessions = await orchestrator.assign_training(user_id, db)
            await db.commit()

            logger.info(
                "training_assigned",
                user_id=str(user_id),
                session_count=len(sessions),
            )
        except Exception:
            await db.rollback()
            logger.exception("training_assignment_failed", user_id=str(user_id))
            raise
