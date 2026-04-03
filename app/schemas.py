import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


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


class ExtractionFieldRule(BaseModel):
    type: str = Field(pattern="^(text|attr|regex|path)$")
    selector: str | None = None
    attr: str | None = None
    path: list[str | int] | None = None
    source_field: str | None = None
    pattern: str | None = None
    group: int = 1
    absolute_url: bool = False
    default: str | None = None

    @model_validator(mode="after")
    def validate_rule(self) -> "ExtractionFieldRule":
        if self.type in {"text", "attr"} and not self.selector:
            raise ValueError("selector is required for text and attr extraction rules")
        if self.type == "attr" and not self.attr:
            raise ValueError("attr is required for attr extraction rules")
        if self.type == "path" and not self.path:
            raise ValueError("path is required for path extraction rules")
        if self.type == "regex" and (not self.source_field or not self.pattern):
            raise ValueError("source_field and pattern are required for regex extraction rules")
        return self


class PaginationRule(BaseModel):
    type: str = Field(default="none", pattern="^(none|query_param)$")
    param: str | None = None
    start_page: int = 1

    @model_validator(mode="after")
    def validate_rule(self) -> "PaginationRule":
        if self.type == "query_param" and not self.param:
            raise ValueError("param is required when pagination type is query_param")
        return self


class ListingExtractionConfig(BaseModel):
    extraction_kind: str = Field(pattern="^(css|json_ld_item_list)$")
    item_selector: str | None = None
    json_ld_selector: str | None = "script[type='application/ld+json']"
    item_path: list[str | int] | None = None
    fields: dict[str, ExtractionFieldRule]
    pagination: PaginationRule = Field(default_factory=PaginationRule)

    @model_validator(mode="after")
    def validate_listing(self) -> "ListingExtractionConfig":
        if self.extraction_kind == "css" and not self.item_selector:
            raise ValueError("item_selector is required for css extraction")
        if self.extraction_kind == "json_ld_item_list" and not self.item_path:
            raise ValueError("item_path is required for json_ld_item_list extraction")
        return self


class DetailExtractionConfig(BaseModel):
    extraction_kind: str = Field(default="css", pattern="^(css|json_ld_item_list)$")
    item_selector: str | None = None
    json_ld_selector: str | None = "script[type='application/ld+json']"
    item_path: list[str | int] | None = None
    fields: dict[str, ExtractionFieldRule]


class FetchConfig(BaseModel):
    mode: str = Field(default="http", pattern="^(http|browser)$")
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    wait_for_selector: str | None = None


class ScraperConfigPayload(BaseModel):
    source_name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=100)
    allowed_domains: list[str] = Field(default_factory=list)
    listing: ListingExtractionConfig
    detail: DetailExtractionConfig | None = None
    fetch: FetchConfig = Field(default_factory=FetchConfig)
    dedupe_keys: list[str] = Field(default_factory=lambda: ["detail_url", "website_url", "company_name"])


class ScraperConfigCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=100)
    status: str = "draft"
    config: ScraperConfigPayload


class ScraperConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_name: str
    version: str
    status: str
    config: dict
    success_rate: float | None
    last_validated_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class DiscoveryPreviewRequest(BaseModel):
    directory_url: HttpUrl
    config: ScraperConfigPayload
    max_pages: int = Field(default=1, ge=1, le=10)
    max_items: int = Field(default=25, ge=1, le=200)


class DiscoveryCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    company_name: str
    website_url: str | None = None
    detail_url: str | None = None
    source_payload: dict = Field(default_factory=dict)


class DiscoveryPreviewResponse(BaseModel):
    source_name: str
    directory_url: str
    fetch_mode: str
    candidates: list[DiscoveryCandidate]
    stats: dict


class DiscoveryRunRequest(BaseModel):
    campaign_id: uuid.UUID
    directory_url: HttpUrl
    config_id: uuid.UUID | None = None
    config: ScraperConfigPayload | None = None
    max_pages: int = Field(default=1, ge=1, le=10)
    max_items: int = Field(default=50, ge=1, le=500)
    enqueue_enrichment: bool = False

    @model_validator(mode="after")
    def validate_config_choice(self) -> "DiscoveryRunRequest":
        if not self.config_id and not self.config:
            raise ValueError("either config_id or config is required")
        return self


class DiscoveryRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trace_id: uuid.UUID
    campaign_id: uuid.UUID
    scraper_config_id: uuid.UUID | None
    source_name: str
    directory_url: str
    status: str
    stats: dict
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
