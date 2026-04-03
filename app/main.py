import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, engine, get_db
from app.logging_utils import configure_logging, get_logger, trace_id_var
from app.models import Campaign, Lead
from app.queue import get_redis_client
from app.schemas import CampaignCreate, CampaignRead, LeadCreate, LeadRead, QueueJobRead
from app.services import create_campaign, create_lead, enqueue_enrichment_job, get_lead, list_campaigns, list_leads


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
