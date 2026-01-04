"""Supabase setup helpers.

This project uses Supabase as the backend for:
- Postgres tables (crawl_queue, raw_ingest, ocr_queue, audit_logs)
- Storage bucket for downloaded assets (PDFs/images)

Server-side scripts should use the *service role* key.
"""

from __future__ import annotations

import os
from typing import Optional


# Load local .env if present so scripts work without manually exporting vars.
# Keep this best-effort: the project still supports using real environment variables.
try:  # pragma: no cover
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(override=False)
except Exception:
    pass


_SUPABASE_CLIENT = None


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_supabase_url() -> str:
    return _require_env("SUPABASE_URL")


def get_supabase_key() -> str:
    # Prefer service role for server scripts; anon key is allowed for read-only/local experimentation.
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY") or _require_env("SUPABASE_ANON_KEY")


def get_storage_bucket() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET", "assets")


def get_supabase():
    """Return a singleton supabase client."""
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    try:
        from supabase import create_client  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Supabase client not installed. Install: pip install supabase"
        ) from e

    _SUPABASE_CLIENT = create_client(get_supabase_url(), get_supabase_key())
    return _SUPABASE_CLIENT
