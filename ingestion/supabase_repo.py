"""Supabase repository + storage helpers used by ingestion/OCR.

This module intentionally wraps supabase-py so the rest of the codebase
can stay testable (unit tests can inject fakes for this interface).

Expected Supabase tables (recommended minimal schema):
- crawl_queue
- raw_ingest
- ocr_queue
- audit_logs

Storage:
- One bucket (default: "assets") with object paths like:
  - pdfs-raw/<context_id>/<filename>
  - images-raw/<context_id>/<filename>
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from supabase_setup import get_supabase, get_storage_bucket


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SupabaseRepo:
    supabase: Any
    storage_bucket: str

    @classmethod
    def from_env(cls) -> "SupabaseRepo":
        return cls(supabase=get_supabase(), storage_bucket=get_storage_bucket())

    # -------------------------
    # Storage
    # -------------------------
    def upload_bytes(self, path: str, data: bytes, content_type: str) -> None:
        # supabase-py accepts bytes or file-like objects depending on version.
        # bytes works with current supabase-py; keep it simple.
        self.supabase.storage.from_(self.storage_bucket).upload(
            path,
            data,
            file_options={"content-type": content_type, "upsert": "true"},
        )

    def download_bytes(self, path: str) -> bytes:
        return self.supabase.storage.from_(self.storage_bucket).download(path)

    # -------------------------
    # raw_ingest
    # -------------------------
    def new_context_id(self) -> str:
        return str(uuid4())

    def upsert_raw_ingest(self, context: Dict[str, Any]) -> str:
        context_id = context.get("context_id") or context.get("id")
        if not context_id:
            raise ValueError("raw_ingest upsert requires context_id")

        row = {
            "id": context_id,
            "url": context.get("url"),
            "content": context.get("content"),
            "provenance": context.get("provenance"),
            "metadata": context.get("metadata"),
            "processing_status": context.get("processing_status"),
            "assets": context.get("assets"),
            "asset_counts": context.get("asset_counts"),
            "priority": context.get("priority"),
        }

        self.supabase.table("raw_ingest").upsert(row).execute()
        return context_id

    def get_raw_ingest(self, context_id: str, columns: str = "*") -> Optional[Dict[str, Any]]:
        resp = self.supabase.table("raw_ingest").select(columns).eq("id", context_id).limit(1).execute()
        data = getattr(resp, "data", None) or []
        if data and isinstance(data, list):
            return data[0]
        return None

    def get_raw_ingest_assets(self, context_id: str) -> Dict[str, Any]:
        row = self.get_raw_ingest(context_id, columns="assets")
        if not row:
            return {}
        return row.get("assets") or {}

    def get_raw_ingest_processing_status(self, context_id: str) -> Dict[str, Any]:
        row = self.get_raw_ingest(context_id, columns="processing_status")
        if not row:
            return {}
        return row.get("processing_status") or {}

    def update_raw_ingest_assets(self, context_id: str, assets: Dict[str, Any], asset_counts: Dict[str, Any]) -> None:
        self.supabase.table("raw_ingest").update(
            {"assets": assets, "asset_counts": asset_counts}
        ).eq("id", context_id).execute()

    def update_raw_ingest_ocr(self, context_id: str, processing_status: Dict[str, Any], ocr: Dict[str, Any]) -> None:
        self.supabase.table("raw_ingest").update(
            {"processing_status": processing_status, "ocr": ocr}
        ).eq("id", context_id).execute()

    # -------------------------
    # audit_logs
    # -------------------------
    def add_audit_log(self, event_type: str, document_id: str, url: Optional[str], success: Optional[bool], details: Optional[Dict[str, Any]] = None) -> None:
        self.supabase.table("audit_logs").insert(
            {
                "id": str(uuid4()),
                "event_type": event_type,
                "document_id": document_id,
                "url": url,
                "success": success,
                "timestamp": utc_now_iso(),
                "details": details,
            }
        ).execute()

    # -------------------------
    # crawl_queue
    # -------------------------
    def crawl_queue_exists_pending(self, url: str) -> bool:
        resp = (
            self.supabase.table("crawl_queue")
            .select("id")
            .eq("url", url)
            .eq("status", "pending")
            .limit(1)
            .execute()
        )
        return bool(getattr(resp, "data", None))

    def insert_crawl_queue(self, entry: Dict[str, Any]) -> str:
        if "id" not in entry:
            entry = {**entry, "id": str(uuid4())}
        if "created_at" not in entry:
            entry = {**entry, "created_at": utc_now_iso()}

        resp = self.supabase.table("crawl_queue").insert(entry).execute()
        # supabase-py returns inserted rows in resp.data
        data = getattr(resp, "data", None) or []
        if data and isinstance(data, list) and data[0].get("id"):
            return data[0]["id"]
        return entry["id"]

    def select_next_crawl_queue(self, limit: int, now_iso: str, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        q = (
            self.supabase.table("crawl_queue")
            .select("*")
            .eq("status", "pending")
            .lte("scheduled_time", now_iso)
            .order("priority_score", desc=True)
            .limit(limit)
        )
        if domain:
            q = q.eq("domain", domain)
        resp = q.execute()
        return list(getattr(resp, "data", None) or [])

    def update_crawl_queue(self, queue_id: str, patch: Dict[str, Any]) -> None:
        self.supabase.table("crawl_queue").update(patch).eq("id", queue_id).execute()

    # -------------------------
    # ocr_queue
    # -------------------------
    def insert_ocr_queue(self, entry: Dict[str, Any]) -> str:
        if "id" not in entry:
            entry = {**entry, "id": str(uuid4())}
        if "created_at" not in entry:
            entry = {**entry, "created_at": utc_now_iso()}

        resp = self.supabase.table("ocr_queue").insert(entry).execute()
        data = getattr(resp, "data", None) or []
        if data and isinstance(data, list) and data[0].get("id"):
            return data[0]["id"]
        return entry["id"]

    def select_pending_ocr(self, limit: int) -> List[Dict[str, Any]]:
        resp = (
            self.supabase.table("ocr_queue")
            .select("*")
            .eq("status", "pending")
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return list(getattr(resp, "data", None) or [])

    def update_ocr_queue(self, queue_id: str, patch: Dict[str, Any]) -> None:
        self.supabase.table("ocr_queue").update(patch).eq("id", queue_id).execute()
