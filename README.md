# Contact Sales Core

Phase 1 deterministic core for the Repeatable Contact Form Sales System.

Included:

- PostgreSQL-backed lead and campaign models
- Redis-backed queue foundation
- deterministic worker process
- request trace IDs and structured JSON logging
- discovery config registry and deterministic scraper runtime
- isolated Docker Compose deployment for VPS use

## Services

- `api`: FastAPI control plane on container port `8000`
- `worker`: deterministic queue worker
- `postgres`: isolated PostgreSQL instance
- `redis`: isolated Redis instance

## Local Run

1. Copy `.env.example` to `.env`
2. Set a strong `POSTGRES_PASSWORD`
3. Run `docker compose up -d --build`

The API binds to `127.0.0.1:${API_HOST_PORT}` only.

## Key Endpoints

- `GET /healthz`
- `GET /readyz`
- `POST /api/v1/campaigns`
- `GET /api/v1/campaigns`
- `POST /api/v1/leads`
- `GET /api/v1/leads`
- `POST /api/v1/leads/{lead_id}/enqueue-enrichment`
- `GET /api/v1/discovery/sample-configs`
- `POST /api/v1/discovery/configs`
- `GET /api/v1/discovery/configs`
- `POST /api/v1/discovery/preview`
- `POST /api/v1/discovery/runs`
- `GET /api/v1/discovery/runs`

## Discovery Engine

Phase 2 adds a deterministic discovery engine that accepts a directory URL plus a typed JSON scraper config.

Supported listing extraction modes:

- `css`: scrape repeated listing cards with CSS selectors
- `json_ld_item_list`: scrape structured `application/ld+json` item lists

Supported fetch modes:

- `http`: direct HTML fetch
- `browser`: headless Chromium fetch for directories that require client-side rendering or bot protection handling

Bundled sample config templates are included for:

- Clutch
- Webflow Certified Partners
- Shopify Partners Directory

## Deployment Shape

This project is intended to be deployed like the other VPS-managed apps:

- project root under `/opt/contact_sales/prod`
- standalone Compose project name: `contact_sales_core`
- dedicated volumes:
  - `contact_sales_core_postgres_data`
  - `contact_sales_core_redis_data`
- no nginx exposure by default
