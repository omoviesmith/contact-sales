import json
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from redis import Redis
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.discovery.engine import run_scraper
from app.logging_utils import get_logger
from app.models import AuditLog, Campaign, DiscoveryRun, Lead, ScraperConfig
from app.schemas import ScraperConfigPayload


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


def create_scraper_config(
    db: Session,
    *,
    source_name: str,
    version: str,
    status: str,
    config: ScraperConfigPayload,
) -> ScraperConfig:
    record = ScraperConfig(
        source_name=source_name,
        version=version,
        status=status,
        config=config.model_dump(mode="json"),
        last_validated_at=datetime.now(UTC),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_scraper_configs(db: Session) -> list[ScraperConfig]:
    statement: Select[tuple[ScraperConfig]] = select(ScraperConfig).order_by(
        ScraperConfig.source_name.asc(),
        ScraperConfig.created_at.desc(),
    )
    return list(db.scalars(statement))


def get_scraper_config(db: Session, scraper_config_id: uuid.UUID) -> ScraperConfig | None:
    return db.get(ScraperConfig, scraper_config_id)


def list_discovery_runs(db: Session) -> list[DiscoveryRun]:
    return list(db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.created_at.desc())))


def _normalize_candidate(candidate: dict) -> dict:
    normalized = {key: value for key, value in candidate.items() if value not in (None, "", [])}
    normalized["company_name"] = normalized.get("company_name") or "Unknown Company"
    return normalized


def _candidate_identity(candidate: dict, dedupe_keys: list[str]) -> str:
    for key in dedupe_keys:
        value = candidate.get(key)
        if value:
            return f"{key}:{str(value).strip().lower()}"
    return f"company_name:{candidate['company_name'].strip().lower()}"


def _lead_exists_for_identity(db: Session, campaign_id: uuid.UUID, identity: str) -> bool:
    statement = select(func.count()).select_from(Lead).where(
        Lead.campaign_id == campaign_id,
        Lead.source_payload["discovery_identity"].astext == identity,
    )
    return bool(db.scalar(statement))


def preview_discovery(
    *,
    directory_url: str,
    config: ScraperConfigPayload,
    max_pages: int,
    max_items: int,
) -> tuple[list[dict], dict]:
    hostname = (urlparse(directory_url).hostname or "").lower()
    if config.allowed_domains and not any(
        hostname == domain.lower() or hostname.endswith(f".{domain.lower()}") for domain in config.allowed_domains
    ):
        raise ValueError(f"directory_url host '{hostname}' is not allowed for source '{config.source_name}'")
    raw_items, stats = run_scraper(
        directory_url=directory_url,
        config=config,
        max_pages=max_pages,
        max_items=max_items,
    )
    candidates = [_normalize_candidate(item) for item in raw_items]
    stats["candidates_normalized"] = len(candidates)
    return candidates, stats


def execute_discovery_run(
    db: Session,
    *,
    campaign: Campaign,
    directory_url: str,
    config: ScraperConfigPayload,
    scraper_config_id: uuid.UUID | None,
    trace_id: uuid.UUID,
    max_pages: int,
    max_items: int,
    enqueue_enrichment: bool,
    redis_client: Redis | None = None,
) -> DiscoveryRun:
    candidates, stats = preview_discovery(
        directory_url=directory_url,
        config=config,
        max_pages=max_pages,
        max_items=max_items,
    )

    run = DiscoveryRun(
        trace_id=trace_id,
        campaign_id=campaign.id,
        scraper_config_id=scraper_config_id,
        source_name=config.source_name,
        directory_url=directory_url,
        status="completed",
        stats={},
    )
    db.add(run)
    db.flush()

    created = 0
    duplicates = 0
    queued = 0

    for candidate in candidates:
        identity = _candidate_identity(candidate, config.dedupe_keys)
        if _lead_exists_for_identity(db, campaign.id, identity):
            duplicates += 1
            continue

        lead = create_lead(
            db,
            campaign_id=campaign.id,
            company_name=candidate["company_name"],
            website_url=candidate.get("website_url"),
            status_reason="discovered_from_directory",
            source_payload={
                "discovery_source": config.source_name,
                "discovery_identity": identity,
                "directory_url": directory_url,
                "directory_candidate": candidate,
            },
            trace_id=trace_id,
        )
        created += 1
        if enqueue_enrichment and redis_client is not None:
            enqueue_enrichment_job(db, redis_client, lead)
            queued += 1

    run.stats = {
        **stats,
        "candidates_considered": len(candidates),
        "leads_created": created,
        "duplicates_skipped": duplicates,
        "enrichment_jobs_queued": queued,
    }
    append_audit_log(
        db,
        trace_id=trace_id,
        campaign_id=campaign.id,
        event_type="discovery.run_completed",
        actor="discovery_engine",
        payload={
            "discovery_run_id": str(run.id),
            "source_name": config.source_name,
            "directory_url": directory_url,
            "stats": run.stats,
        },
    )
    db.commit()
    db.refresh(run)
    return run
