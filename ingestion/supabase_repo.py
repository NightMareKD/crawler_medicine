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

    # -------------------------
    # Corpus Annotation Methods
    # -------------------------
    
    def update_language_annotation(
        self,
        context_id: str,
        detected_language: str,
        language_confidence: float,
        is_romanized: bool = False,
        romanized_type: Optional[str] = None
    ) -> None:
        """Update language detection results for a document."""
        patch = {
            "detected_language": detected_language,
            "language_confidence": language_confidence,
            "is_romanized": is_romanized,
            "romanized_type": romanized_type,
        }
        # Also update processing_status
        current_status = self.get_raw_ingest_processing_status(context_id)
        current_status["language_detected"] = True
        current_status["language_detected_at"] = utc_now_iso()
        patch["processing_status"] = current_status
        
        self.supabase.table("raw_ingest").update(patch).eq("id", context_id).execute()
    
    def update_entities(self, context_id: str, entities: List[Dict[str, Any]]) -> None:
        """Update extracted entities for a document."""
        current_status = self.get_raw_ingest_processing_status(context_id)
        current_status["entities_extracted"] = True
        current_status["entities_extracted_at"] = utc_now_iso()
        
        self.supabase.table("raw_ingest").update({
            "entities": entities,
            "processing_status": current_status,
        }).eq("id", context_id).execute()
    
    def update_intent_domain(
        self,
        context_id: str,
        intent: Optional[str],
        domain: Optional[str]
    ) -> None:
        """Update intent and domain classification."""
        patch: Dict[str, Any] = {}
        if intent:
            patch["intent"] = intent
        if domain:
            patch["domain"] = domain
        if patch:
            self.supabase.table("raw_ingest").update(patch).eq("id", context_id).execute()
    
    def update_translated_text(
        self,
        context_id: str,
        translations: Dict[str, str]
    ) -> None:
        """Update translated text versions."""
        self.supabase.table("raw_ingest").update({
            "translated_text": translations
        }).eq("id", context_id).execute()
    
    def update_content_hash(self, context_id: str, content_hash: str) -> None:
        """Update content hash for deduplication."""
        self.supabase.table("raw_ingest").update({
            "content_hash": content_hash
        }).eq("id", context_id).execute()
    
    def find_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Find document by content hash."""
        resp = (
            self.supabase.table("raw_ingest")
            .select("id,url,created_at")
            .eq("content_hash", content_hash)
            .limit(1)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        return data[0] if data else None

    # -------------------------
    # Q&A Pairs
    # -------------------------
    
    def insert_qa_pair(self, qa_pair: Dict[str, Any]) -> str:
        """Insert a Q&A pair."""
        if "id" not in qa_pair:
            qa_pair = {**qa_pair, "id": str(uuid4())}
        if "created_at" not in qa_pair:
            qa_pair = {**qa_pair, "created_at": utc_now_iso()}
        
        resp = self.supabase.table("qa_pairs").insert(qa_pair).execute()
        data = getattr(resp, "data", None) or []
        if data and isinstance(data, list) and data[0].get("id"):
            return data[0]["id"]
        return qa_pair["id"]
    
    def get_qa_pairs(
        self,
        limit: int = 100,
        language: Optional[str] = None,
        domain: Optional[str] = None,
        verified_only: bool = False
    ) -> List[Dict[str, Any]]:
        """Get Q&A pairs with optional filters."""
        q = self.supabase.table("qa_pairs").select("*").limit(limit)
        if language:
            q = q.eq("question_language", language)
        if domain:
            q = q.eq("domain", domain)
        if verified_only:
            q = q.eq("verified", True)
        
        resp = q.order("created_at", desc=True).execute()
        return list(getattr(resp, "data", None) or [])
    
    def verify_qa_pair(self, qa_id: str, reviewer_id: str, notes: Optional[str] = None) -> None:
        """Mark a Q&A pair as verified."""
        self.supabase.table("qa_pairs").update({
            "verified": True,
            "reviewer_id": reviewer_id,
            "review_notes": notes,
            "updated_at": utc_now_iso(),
        }).eq("id", qa_id).execute()

    # -------------------------
    # Corpus Statistics
    # -------------------------
    
    def insert_corpus_statistics(self, stats: Dict[str, Any]) -> str:
        """Insert corpus statistics snapshot."""
        if "id" not in stats:
            stats = {**stats, "id": str(uuid4())}
        if "created_at" not in stats:
            stats = {**stats, "created_at": utc_now_iso()}
        
        resp = self.supabase.table("corpus_statistics").insert(stats).execute()
        data = getattr(resp, "data", None) or []
        if data and isinstance(data, list) and data[0].get("id"):
            return data[0]["id"]
        return stats["id"]
    
    def get_latest_corpus_statistics(self) -> Optional[Dict[str, Any]]:
        """Get the most recent corpus statistics."""
        resp = (
            self.supabase.table("corpus_statistics")
            .select("*")
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
        data = getattr(resp, "data", None) or []
        return data[0] if data else None

    # -------------------------
    # Content Versions
    # -------------------------
    
    def insert_content_version(
        self,
        context_id: str,
        content_hash: str,
        version_number: int,
        previous_version_id: Optional[str] = None,
        changes_summary: Optional[str] = None
    ) -> str:
        """Insert a content version record."""
        entry = {
            "id": str(uuid4()),
            "context_id": context_id,
            "content_hash": content_hash,
            "version_number": version_number,
            "previous_version_id": previous_version_id,
            "changes_summary": changes_summary,
            "created_at": utc_now_iso(),
        }
        
        resp = self.supabase.table("content_versions").insert(entry).execute()
        data = getattr(resp, "data", None) or []
        if data and isinstance(data, list) and data[0].get("id"):
            return data[0]["id"]
        return entry["id"]
    
    def get_content_versions(self, context_id: str) -> List[Dict[str, Any]]:
        """Get all versions of a document."""
        resp = (
            self.supabase.table("content_versions")
            .select("*")
            .eq("context_id", context_id)
            .order("version_number", desc=True)
            .execute()
        )
        return list(getattr(resp, "data", None) or [])
