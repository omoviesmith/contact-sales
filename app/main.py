import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_db
from app.discovery.sample_configs import (
    CLUTCH_GENERIC_CONFIG,
    SHOPIFY_PARTNERS_CONFIG,
    WEBFLOW_CERTIFIED_PARTNERS_CONFIG,
)
from app.logging_utils import configure_logging, get_logger, trace_id_var
from app.models import Campaign, Lead
from app.queue import get_redis_client
from app.schemas import (
    CampaignCreate,
    CampaignRead,
    DiscoveryPreviewRequest,
    DiscoveryPreviewResponse,
    DiscoveryRunRead,
    DiscoveryRunRequest,
    EnrichmentPreviewResponse,
    LeadCreate,
    LeadEnrichmentRead,
    LeadRead,
    QueueJobRead,
    ScraperConfigPayload,
    ScraperConfigCreate,
    ScraperConfigRead,
)
from app.services import (
    create_campaign,
    create_lead,
    create_scraper_config,
    enqueue_enrichment_job,
    execute_discovery_run,
    execute_enrichment,
    get_lead,
    get_latest_lead_enrichment,
    get_scraper_config,
    list_campaigns,
    list_discovery_runs,
    list_lead_enrichments,
    list_leads,
    list_scraper_configs,
    preview_enrichment,
    preview_discovery,
)


configure_logging(settings.log_level)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("application startup complete")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.middleware("http")
async def attach_trace_id(request: Request, call_next):
    raw_trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
    try:
        trace_id = str(uuid.UUID(raw_trace_id))
    except ValueError:
        trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    token = trace_id_var.set(trace_id)
    try:
        response = await call_next(request)
    finally:
        trace_id_var.reset(token)
    response.headers["x-trace-id"] = trace_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("unhandled exception")
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)):
    db.execute(text("select 1"))
    redis_client = get_redis_client()
    redis_client.ping()
    return {"status": "ready"}


@app.post("/api/v1/campaigns", response_model=CampaignRead, status_code=201)
def create_campaign_endpoint(payload: CampaignCreate, db: Session = Depends(get_db)):
    existing = db.query(Campaign).filter(Campaign.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="campaign name already exists")
    campaign = create_campaign(db, name=payload.name, status=payload.status, configuration=payload.configuration)
    return campaign


@app.get("/api/v1/campaigns", response_model=list[CampaignRead])
def list_campaigns_endpoint(db: Session = Depends(get_db)):
    return list_campaigns(db)


@app.post("/api/v1/leads", response_model=LeadRead, status_code=201)
def create_lead_endpoint(request: Request, payload: LeadCreate, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    trace_id = uuid.UUID(request.state.trace_id)
    lead = create_lead(
        db,
        campaign_id=payload.campaign_id,
        company_name=payload.company_name,
        website_url=payload.website_url,
        status_reason=payload.status_reason,
        source_payload=payload.source_payload,
        trace_id=trace_id,
    )
    return lead


@app.get("/api/v1/leads", response_model=list[LeadRead])
def list_leads_endpoint(db: Session = Depends(get_db)):
    return list_leads(db)


@app.post("/api/v1/leads/{lead_id}/enqueue-enrichment", response_model=QueueJobRead, status_code=202)
def enqueue_enrichment_endpoint(lead_id: uuid.UUID, db: Session = Depends(get_db)):
    lead = get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    redis_client = get_redis_client()
    return enqueue_enrichment_job(db, redis_client, lead)


@app.post("/api/v1/leads/{lead_id}/enrichment/preview", response_model=EnrichmentPreviewResponse)
def preview_enrichment_endpoint(lead_id: uuid.UUID, db: Session = Depends(get_db)):
    lead = get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return preview_enrichment(lead=lead)


@app.post("/api/v1/leads/{lead_id}/enrichment/run", response_model=LeadEnrichmentRead, status_code=201)
def execute_enrichment_endpoint(request: Request, lead_id: uuid.UUID, db: Session = Depends(get_db)):
    lead = get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return execute_enrichment(db, lead=lead, trace_id=uuid.UUID(request.state.trace_id))


@app.get("/api/v1/leads/{lead_id}/enrichments", response_model=list[LeadEnrichmentRead])
def list_lead_enrichments_endpoint(lead_id: uuid.UUID, db: Session = Depends(get_db)):
    lead = get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return list_lead_enrichments(db, lead_id)


@app.get("/api/v1/leads/{lead_id}/enrichment/latest", response_model=LeadEnrichmentRead)
def get_latest_lead_enrichment_endpoint(lead_id: uuid.UUID, db: Session = Depends(get_db)):
    lead = get_lead(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    enrichment = get_latest_lead_enrichment(db, lead_id)
    if not enrichment:
        raise HTTPException(status_code=404, detail="lead enrichment not found")
    return enrichment


@app.get("/api/v1/discovery/sample-configs")
def list_discovery_sample_configs():
    return {
        "clutch": CLUTCH_GENERIC_CONFIG,
        "webflow_certified_partners": WEBFLOW_CERTIFIED_PARTNERS_CONFIG,
        "shopify_partners_directory": SHOPIFY_PARTNERS_CONFIG,
    }


@app.post("/api/v1/discovery/configs", response_model=ScraperConfigRead, status_code=201)
def create_scraper_config_endpoint(payload: ScraperConfigCreate, db: Session = Depends(get_db)):
    return create_scraper_config(
        db,
        source_name=payload.source_name,
        version=payload.version,
        status=payload.status,
        config=payload.config,
    )


@app.get("/api/v1/discovery/configs", response_model=list[ScraperConfigRead])
def list_scraper_configs_endpoint(db: Session = Depends(get_db)):
    return list_scraper_configs(db)


@app.post("/api/v1/discovery/preview", response_model=DiscoveryPreviewResponse)
def discovery_preview_endpoint(payload: DiscoveryPreviewRequest):
    try:
        candidates, stats = preview_discovery(
            directory_url=str(payload.directory_url),
            config=payload.config,
            max_pages=payload.max_pages,
            max_items=payload.max_items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "source_name": payload.config.source_name,
        "directory_url": str(payload.directory_url),
        "fetch_mode": payload.config.fetch.mode,
        "candidates": candidates,
        "stats": stats,
    }


@app.post("/api/v1/discovery/runs", response_model=DiscoveryRunRead, status_code=201)
def execute_discovery_run_endpoint(request: Request, payload: DiscoveryRunRequest, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, payload.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")

    scraper_config_id = payload.config_id
    config = payload.config
    if scraper_config_id:
        record = get_scraper_config(db, scraper_config_id)
        if not record:
            raise HTTPException(status_code=404, detail="scraper config not found")
        config = record.config
    if config is None:
        raise HTTPException(status_code=400, detail="scraper config is required")
    typed_config = config if isinstance(config, ScraperConfigPayload) else ScraperConfigPayload.model_validate(config)

    try:
        run = execute_discovery_run(
            db,
            campaign=campaign,
            directory_url=str(payload.directory_url),
            config=typed_config,
            scraper_config_id=scraper_config_id,
            trace_id=uuid.UUID(request.state.trace_id),
            max_pages=payload.max_pages,
            max_items=payload.max_items,
            enqueue_enrichment=payload.enqueue_enrichment,
            redis_client=get_redis_client() if payload.enqueue_enrichment else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run


@app.get("/api/v1/discovery/runs", response_model=list[DiscoveryRunRead])
def list_discovery_runs_endpoint(db: Session = Depends(get_db)):
    return list_discovery_runs(db)
