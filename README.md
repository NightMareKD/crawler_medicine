# crawl4ai

Supabase-backed ingestion layer that crawls public health/government sites and writes “context objects” into Postgres (via Supabase), with assets stored in Supabase Storage.

## What’s in here

- Ingestion pipeline:
  - crawler: `ingestion/crawler_agent.py`
  - asset segregation + Storage upload: `ingestion/asset_segregator.py`
  - crawl queue manager: `ingestion/url_manager.py`
  - orchestrator: `run_ingestion.py`
- OCR worker: `run_ocr.py`
- Supabase wiring:
  - client bootstrap: `supabase_setup.py`
  - repo wrapper: `ingestion/supabase_repo.py`

## Required environment variables

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (recommended) or `SUPABASE_ANON_KEY`
- `SUPABASE_STORAGE_BUCKET` (default: `assets`)

Create a local `.env` from `.env.example` (the repo does not ship credentials).

## Install

```powershell
python -m venv .venv
\.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If you want to run the Crawl4AI-based crawler agent, also install:

```powershell
pip install -r requirements-crawler.txt
```

## Database + Storage setup (Supabase)

This project expects these Postgres tables to exist:

- `crawl_queue`
- `raw_ingest`
- `ocr_queue`
- `audit_logs`

Minimal (suggested) schema:

```sql
create table if not exists crawl_queue (
  id text primary key,
  url text not null,
  domain text,
  source_agency text,
  priority text,
  priority_score double precision,
  status text not null,
  scheduled_time timestamptz,
  attempts integer default 0,
  max_attempts integer default 3,
  last_error text,
  last_attempt_at timestamptz,
  processing_started_at timestamptz,
  completed_at timestamptz,
  context_id text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create table if not exists raw_ingest (
  id text primary key,
  url text,
  content jsonb,
  provenance jsonb default '{}'::jsonb,
  metadata jsonb default '{}'::jsonb,
  processing_status jsonb default '{}'::jsonb,
  assets jsonb default '{}'::jsonb,
  asset_counts jsonb default '{}'::jsonb,
  ocr jsonb default '{}'::jsonb,
  priority text,
  created_at timestamptz default now()
);

create table if not exists ocr_queue (
  id text primary key,
  context_id text not null,
  storage_path text not null,
  asset_type text not null,
  priority text,
  status text not null,
  attempts integer default 0,
  max_attempts integer default 3,
  processing_started_at timestamptz,
  completed_at timestamptz,
  failed_at timestamptz,
  last_error text,
  result jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);

create table if not exists audit_logs (
  id text primary key,
  event_type text not null,
  document_id text not null,
  url text,
  success boolean,
  timestamp timestamptz default now(),
  details jsonb default '{}'::jsonb
);

create index if not exists idx_crawl_queue_status_priority on crawl_queue (status, priority_score desc);
create index if not exists idx_crawl_queue_scheduled_time on crawl_queue (scheduled_time);
create index if not exists idx_ocr_queue_status_created_at on ocr_queue (status, created_at);
create index if not exists idx_ocr_queue_status_priority on ocr_queue (status, priority);
```

Also create a Supabase Storage bucket named `assets` (or set `SUPABASE_STORAGE_BUCKET`).

## Run tests

Unit tests:

```powershell
pytest -v
```

Integration tests (opt-in):

```powershell
$env:RUN_INGESTION_INTEGRATION_TESTS="1"
pytest test_ingestion_layer.py -v
```

## Run ingestion

The ingestion entrypoint is the `IngestionOrchestrator` in `run_ingestion.py`.

## Run OCR worker

```powershell
python run_ocr.py
```

