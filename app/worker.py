import json
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.logging_utils import configure_logging, get_logger, trace_id_var
from app.models import Lead
from app.queue import get_redis_client
from app.services import append_audit_log, execute_enrichment


configure_logging(settings.log_level)
logger = get_logger(__name__)


def process_job(db: Session, payload: dict) -> None:
    trace_id = payload.get("trace_id", str(uuid.uuid4()))
    token = trace_id_var.set(trace_id)
    try:
        lead = db.get(Lead, uuid.UUID(payload["lead_id"]))
        if not lead:
            logger.warning("lead missing for job", extra={"extra_fields": {"job_id": payload["job_id"]}})
            return
        if payload["type"] != "lead.enrichment":
            logger.warning(
                "unsupported job type",
                extra={"extra_fields": {"job_id": payload["job_id"], "job_type": payload["type"]}},
            )
            return
        result = execute_enrichment(db, lead=lead, trace_id=uuid.UUID(trace_id))
        append_audit_log(
            db,
            trace_id=uuid.UUID(trace_id),
            lead_id=lead.id,
            campaign_id=lead.campaign_id,
            event_type="worker.job_completed",
            actor="worker",
            payload={
                "job_id": payload["job_id"],
                "job_type": payload["type"],
                "enrichment_status": result.status,
                "lead_state": lead.state,
            },
        )
        db.commit()
        logger.info(
            "processed job",
            extra={
                "extra_fields": {
                    "job_id": payload["job_id"],
                    "lead_id": str(lead.id),
                    "new_state": lead.state,
                    "enrichment_status": result.status,
                }
            },
        )
    finally:
        trace_id_var.reset(token)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    redis_client = get_redis_client()
    logger.info("worker started", extra={"extra_fields": {"queue_name": settings.queue_name}})
    while True:
        item = redis_client.blpop(settings.queue_name, timeout=settings.worker_poll_seconds)
        if not item:
            continue
        _, raw_payload = item
        payload = json.loads(raw_payload)
        with SessionLocal() as db:
            process_job(db, payload)
        time.sleep(0.1)


if __name__ == "__main__":
    main()
