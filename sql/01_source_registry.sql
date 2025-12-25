-- Step 1: Source registry + crawl run tracking
--
-- This schema is additive: it doesn't modify existing tables.
-- Apply it in Supabase SQL editor.

create table if not exists sources (
  id text primary key,
  agency text not null,
  country text,
  region text,
  reliability double precision,
  user_demand double precision,
  language_targets jsonb default '{}'::jsonb,
  topics jsonb default '[]'::jsonb,
  seed_urls jsonb default '[]'::jsonb,
  notes text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists source_topics (
  id text primary key,
  source_id text not null references sources(id) on delete cascade,
  topic text not null,
  created_at timestamptz default now()
);

create table if not exists crawl_runs (
  id text primary key,
  started_at timestamptz default now(),
  finished_at timestamptz,
  status text not null default 'running',
  config jsonb default '{}'::jsonb,
  stats jsonb default '{}'::jsonb
);

create index if not exists idx_sources_country_region on sources(country, region);
create index if not exists idx_source_topics_source_id on source_topics(source_id);
