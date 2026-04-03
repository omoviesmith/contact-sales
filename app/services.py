import json
import uuid
from datetime import UTC, datetime

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.logging_utils import get_logger
from app.models import AuditLog, Campaign, Lead


logger = get_logger(__name__)


def append_audit_log(
    db: Session,
    *,
    trace_id: uuid.UUID,
    event_type: str,
    actor: str = "system",
    lead_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    payload: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        trace_id=trace_id,
        lead_id=lead_id,
        campaign_id=campaign_id,
        event_type=event_type,
        actor=actor,
        payload=payload or {},
    )
    db.add(entry)
    return entry


def create_campaign(db: Session, *, name: str, status: str, configuration: dict) -> Campaign:
    campaign = Campaign(name=name, status=status, configuration=configuration)
    db.add(campaign)
    db.flush()
    append_audit_log(
        db,
        trace_id=uuid.uuid4(),
        campaign_id=campaign.id,
        event_type="campaign.created",
        payload={"name": name, "status": status},
    )
    db.commit()
    db.refresh(campaign)
    return campaign


def list_campaigns(db: Session) -> list[Campaign]:
    return list(db.scalars(select(Campaign).order_by(Campaign.created_at.desc())))


def create_lead(
    db: Session,
    *,
    campaign_id: uuid.UUID,
    company_name: str,
    website_url: str | None,
    status_reason: str | None,
    source_payload: dict,
    trace_id: uuid.UUID,
) -> Lead:
    lead = Lead(
        trace_id=trace_id,
        campaign_id=campaign_id,
        company_name=company_name,
        website_url=website_url,
        status_reason=status_reason,
        source_payload=source_payload,
    )
    db.add(lead)
    db.flush()
    append_audit_log(
        db,
        trace_id=trace_id,
        lead_id=lead.id,
        campaign_id=campaign_id,
        event_type="lead.created",
        payload={"company_name": company_name, "state": lead.state},
    )
    db.commit()
    db.refresh(lead)
    return lead


def list_leads(db: Session) -> list[Lead]:
    return list(db.scalars(select(Lead).order_by(Lead.created_at.desc())))


def get_lead(db: Session, lead_id: uuid.UUID) -> Lead | None:
    return db.get(Lead, lead_id)


def enqueue_enrichment_job(db: Session, redis_client: Redis, lead: Lead) -> dict:
    lead.state = "enrichment_pending"
    lead.updated_at = datetime.now(UTC)
    append_audit_log(
        db,
        trace_id=lead.trace_id,
        lead_id=lead.id,
        campaign_id=lead.campaign_id,
        event_type="lead.enrichment_queued",
        payload={"queue": settings.queue_name},
    )
    db.commit()

    job_id = str(uuid.uuid4())
    payload = {
        "job_id": job_id,
        "type": "lead.enrichment_placeholder",
        "lead_id": str(lead.id),
        "campaign_id": str(lead.campaign_id),
        "trace_id": str(lead.trace_id),
        "queued_at": datetime.now(UTC).isoformat(),
    }
    redis_client.rpush(settings.queue_name, json.dumps(payload))
    logger.info(
        "queued job",
        extra={"extra_fields": {"job_id": job_id, "lead_id": str(lead.id), "queue_name": settings.queue_name}},
    )
    return {"job_id": job_id, "queue_name": settings.queue_name, "status": "queued"}
