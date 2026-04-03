# Contact Sales Core

Phase 1 deterministic core for the Repeatable Contact Form Sales System.

Included:

- PostgreSQL-backed lead and campaign models
- Redis-backed queue foundation
- deterministic worker process
- request trace IDs and structured JSON logging
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

## Deployment Shape

This project is intended to be deployed like the other VPS-managed apps:

- project root under `/opt/contact_sales/prod`
- standalone Compose project name: `contact_sales_core`
- dedicated volumes:
  - `contact_sales_core_postgres_data`
  - `contact_sales_core_redis_data`
- no nginx exposure by default
