"""Unit tests for the Crawl4AI ingestion + OCR integration (Supabase edition).

These tests are designed to run WITHOUT:
- Real Supabase credentials
- Network calls
- Crawl4AI installed

They use small fakes/mocks to validate behavior and integration points.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest


# -------------------------
# Fakes (SupabaseRepo-like)
# -------------------------


class FakeRepo:
    def __init__(self, blobs: Dict[str, bytes]):
        self._blobs = dict(blobs)
        self.ocr_queue_updates: Dict[str, Dict[str, Any]] = {}
        self.raw_ingest_processing_status: Dict[str, Dict[str, Any]] = {}
        self.raw_ingest_ocr: Dict[str, Dict[str, Any]] = {}

    def select_pending_ocr(self, limit: int = 5):
        return []

    def download_bytes(self, path: str) -> bytes:
        if path not in self._blobs:
            raise FileNotFoundError(path)
        return self._blobs[path]

    def update_ocr_queue(self, queue_id: str, patch: Dict[str, Any]) -> None:
        existing = self.ocr_queue_updates.get(queue_id, {})
        existing.update(patch)
        self.ocr_queue_updates[queue_id] = existing

    def get_raw_ingest_processing_status(self, context_id: str) -> Dict[str, Any]:
        return dict(self.raw_ingest_processing_status.get(context_id, {}))

    def update_raw_ingest_ocr(self, context_id: str, processing_status: Dict[str, Any], ocr: Dict[str, Any]) -> None:
        self.raw_ingest_processing_status[context_id] = dict(processing_status)
        self.raw_ingest_ocr[context_id] = dict(ocr)


# -------------------------
# Tests
# -------------------------


def test_url_manager_priority_scoring_is_bounded():
    from ingestion.url_manager import URLManager

    # URLManager normally requires a repo in __init__; bypass init for pure scoring.
    mgr = URLManager.__new__(URLManager)
    score = mgr.calculate_priority_score(
        url="http://www.epid.gov.lk/",
        priority_level="high",
        freshness_days=90,
        user_demand=1.0,
    )
    assert 0.0 <= score <= 1.0


def test_asset_segregator_detects_pdf_and_image_without_backend():
    from ingestion.asset_segregator import AssetSegregator

    seg = AssetSegregator.__new__(AssetSegregator)  # bypass repo init

    assert seg.detect_asset_type("https://example.com/report.pdf") == "pdf"
    assert seg.detect_asset_type("https://example.com/photo.png") == "image"
    assert seg.detect_asset_type("https://example.com/") == "html"


def test_ocr_processor_writes_results_to_supabase_repo():
    from ingestion.ocr_processor import OCRProcessor

    repo = FakeRepo({"pdfs-raw/ctx1/a.pdf": b"%PDF-1.4\n%fake\n"})

    class StubBackend:
        def extract_text_pdf(self, data: bytes) -> str:
            assert data.startswith(b"%PDF")
            return "hello from pdf"

        def extract_text_image(self, data: bytes) -> str:
            raise AssertionError("not used")

    repo.raw_ingest_processing_status["ctx1"] = {"ocr_required": True}

    processor = OCRProcessor(repo=repo, backend=StubBackend())

    entry = {
        "storage_path": "pdfs-raw/ctx1/a.pdf",
        "context_id": "ctx1",
        "asset_type": "pdf",
        "status": "pending",
        "attempts": 0,
    }

    result = processor.process_queue_entry("q1", entry)
    assert result.text == "hello from pdf"

    assert repo.raw_ingest_processing_status["ctx1"]["ocr_completed"] is True
    assert repo.raw_ingest_ocr["ctx1"]["text"] == "hello from pdf"

    q = repo.ocr_queue_updates["q1"]
    assert q["status"] == "completed"
    assert q["result"]["text_length"] == len("hello from pdf")


def test_ingestion_package_import_is_safe_without_crawl4ai(monkeypatch):
    """Importing ingestion should not crash if Crawl4AI isn't installed.

    We only assert that the package itself imports; individual modules may still
    require optional deps.
    """

    # Ensure "crawl4ai" is not importable in this test
    monkeypatch.setitem(__import__("sys").modules, "crawl4ai", None)

    import importlib

    importlib.reload(importlib.import_module("ingestion"))
