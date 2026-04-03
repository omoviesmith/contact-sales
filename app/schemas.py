import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    status: str = "draft"
    configuration: dict = Field(default_factory=dict)


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: str
    configuration: dict
    created_at: datetime
    updated_at: datetime


class LeadCreate(BaseModel):
    campaign_id: uuid.UUID
    company_name: str = Field(min_length=1, max_length=255)
    website_url: str | None = None
    status_reason: str | None = None
    source_payload: dict = Field(default_factory=dict)


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_id: uuid.UUID
    campaign_id: uuid.UUID
    company_name: str
    website_url: str | None
    state: str
    status_reason: str | None
    confidence_summary: dict
    last_agent_decision: dict
    reply_classification: dict
    follow_up_eligibility: str
    created_at: datetime
    updated_at: datetime


class QueueJobRead(BaseModel):
    job_id: str
    queue_name: str
    status: str
