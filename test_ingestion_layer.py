"""Integration tests for the ingestion layer.

This file used to be an interactive async script; pytest would collect its
`test_*` coroutines and fail. It is now a proper integration test module.

By default, these tests are skipped to keep `pytest` green without requiring
real Supabase credentials or network crawling.

Enable explicitly:
  - Set `RUN_INGESTION_INTEGRATION_TESTS=1`

Optional crawler smoke:
  - Set `RUN_CRAWLER_SMOKE=1`
  - Install crawler deps: `pip install -r requirements-crawler.txt`
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest


def _env_is_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "y"}


if not _env_is_truthy("RUN_INGESTION_INTEGRATION_TESTS"):
    pytest.skip(
        "Skipping ingestion integration tests. Set RUN_INGESTION_INTEGRATION_TESTS=1 to enable.",
        allow_module_level=True,
    )


@pytest.fixture(scope="session")
def supabase_ready():
    """Initialize Supabase repo using env vars.

    Requires:
      - SUPABASE_URL
      - SUPABASE_SERVICE_ROLE_KEY (recommended)
    """
    if not os.getenv("SUPABASE_URL"):
        pytest.skip("SUPABASE_URL not set")
    if not (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")):
        pytest.skip("SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY not set")

    from ingestion.supabase_repo import SupabaseRepo

    return SupabaseRepo.from_env()


def test_url_manager_adds_and_reads_queue(supabase_ready):
    from ingestion.url_manager import URLManager

    mgr = URLManager(repo=supabase_ready)

    url = f"https://example.com/health-bulletin?t={int(time.time())}"
    doc_id = mgr.add_url(
        url=url,
        priority="high",
        source_config={"agency": "Test", "reliability": 0.9},
    )
    assert doc_id is not None

    next_urls = mgr.get_next_urls(limit=10)
    assert any(entry.get("url") == url for entry in next_urls)

    # Cleanup
    supabase_ready.supabase.table("crawl_queue").delete().eq("id", doc_id).execute()


def test_asset_segregator_can_enqueue_ocr(supabase_ready):
    from ingestion.asset_segregator import AssetSegregator

    context_id = f"ctx_{int(time.time())}"

    # Seed raw_ingest row
    supabase_ready.supabase.table("raw_ingest").upsert(
        {"id": context_id, "processing_status": {"ocr_required": True}}
    ).execute()

    seg = AssetSegregator(repo=supabase_ready)
    queue_id = seg.create_ocr_queue_entry(
        storage_path=f"pdfs-raw/{context_id}/a.pdf",
        context_id=context_id,
        asset_type="pdf",
        priority="low",
    )
    assert queue_id

    q_resp = supabase_ready.supabase.table("ocr_queue").select("*").eq("id", queue_id).limit(1).execute()
    q_rows = getattr(q_resp, "data", None) or []
    assert q_rows
    q = q_rows[0]
    assert q.get("status") == "pending"
    assert q.get("context_id") == context_id

    # Cleanup
    supabase_ready.supabase.table("ocr_queue").delete().eq("id", queue_id).execute()
    supabase_ready.supabase.table("raw_ingest").delete().eq("id", context_id).execute()


@pytest.mark.asyncio
async def test_crawler_smoke(supabase_ready):
    if not _env_is_truthy("RUN_CRAWLER_SMOKE"):
        pytest.skip("Set RUN_CRAWLER_SMOKE=1 to enable crawler smoke test")

    try:
        import crawl4ai  # type: ignore  # noqa: F401
    except Exception:
        pytest.skip("crawl4ai not installed (pip install -r requirements-crawler.txt)")

    from ingestion.crawler_agent import AdaptiveCrawlerAgent

    crawler = AdaptiveCrawlerAgent(rate_limit_delay=1.0)
    result = await crawler.crawl(
        url="https://example.com/",
        source_config={"agency": "Test", "reliability": 0.5},
        extraction_strategy="css",
    )

    # This is a smoke test; allow either success or a polite failure.
    assert isinstance(result, dict)
