"""OCR Processor

Consumes OCR work items from Supabase (`ocr_queue`), downloads the referenced asset
from Supabase Storage, extracts text, and writes results back to Postgres (`raw_ingest`).

Design goals:
- Works as a local worker (no Cloud Functions dependency on system Tesseract).
- Uses optional backends (PyMuPDF / pytesseract) when installed.
- Testable without real Supabase via dependency injection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol
import logging
from datetime import datetime, timezone

from ingestion.supabase_repo import utc_now_iso

logger = logging.getLogger(__name__)


class OCRBackend(Protocol):
    def extract_text_pdf(self, data: bytes) -> str:
        ...

    def extract_text_image(self, data: bytes) -> str:
        ...


class OCRRepo(Protocol):
    def update_ocr_queue(self, queue_id: str, patch: Dict[str, Any]) -> None:
        ...

    def download_bytes(self, path: str) -> bytes:
        ...

    def get_raw_ingest_processing_status(self, context_id: str) -> Dict[str, Any]:
        ...

    def update_raw_ingest_ocr(self, context_id: str, processing_status: Dict[str, Any], ocr: Dict[str, Any]) -> None:
        ...

    def select_pending_ocr(self, limit: int) -> List[Dict[str, Any]]:
        ...


@dataclass(frozen=True)
class OCRResult:
    text: str
    backend: str
    processed_at_iso: str


class DefaultOCRBackend:
    """Best-effort OCR backend.

    - PDFs: first try text extraction via PyMuPDF (fast, no OCR).
    - Images: try pytesseract + Pillow.

    If required libraries are missing, raises RuntimeError with actionable message.
    """

    def extract_text_pdf(self, data: bytes) -> str:
        try:
            import fitz  # PyMuPDF
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "PDF extraction requires PyMuPDF. Install: pip install PyMuPDF"
            ) from e

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            chunks = []
            for page in doc:
                chunks.append(page.get_text("text"))
            text = "\n".join(chunks).strip()
            return text
        finally:
            doc.close()

    def extract_text_image(self, data: bytes) -> str:
        try:
            from PIL import Image
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Image OCR requires Pillow. Install: pip install pillow"
            ) from e

        try:
            import pytesseract
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Image OCR requires pytesseract and the system Tesseract binary. "
                "Install: pip install pytesseract, then install Tesseract OCR on the OS."
            ) from e

        import io

        img = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(img)
        return (text or "").strip()


class OCRProcessor:
    def __init__(
        self,
        repo: OCRRepo,
        backend: Optional[OCRBackend] = None,
    ) -> None:
        self.repo = repo
        self.backend = backend or DefaultOCRBackend()

    def process_queue_entry(self, queue_doc_id: str, entry: Dict[str, Any]) -> OCRResult:
        """Process a single OCR queue entry.

        Expected `entry` schema (created by AssetSegregator.create_ocr_queue_entry):
        - storage_path: str
        - context_id: str
        - asset_type: str ('pdf'|'image')
        - status: 'pending'|'processing'|'completed'|'failed'
        """

        storage_path = entry.get("storage_path")
        context_id = entry.get("context_id")
        asset_type = entry.get("asset_type")

        if not storage_path or not context_id or not asset_type:
            raise ValueError("Invalid ocr_queue entry: missing storage_path/context_id/asset_type")

        self.repo.update_ocr_queue(
            queue_doc_id,
            {
                "status": "processing",
                "processing_started_at": utc_now_iso(),
                "attempts": int(entry.get("attempts") or 0) + 1,
            },
        )

        data: bytes = self.repo.download_bytes(storage_path)

        processed_at_iso = datetime.now(timezone.utc).isoformat()

        if asset_type == "pdf":
            text = self.backend.extract_text_pdf(data)
            backend_name = type(self.backend).__name__
        elif asset_type == "image":
            text = self.backend.extract_text_image(data)
            backend_name = type(self.backend).__name__
        else:
            raise ValueError(f"Unsupported asset_type for OCR: {asset_type}")

        result = OCRResult(text=text, backend=backend_name, processed_at_iso=processed_at_iso)

        # Persist OCR output under raw_ingest so downstream steps can consume it
        processing_status = self.repo.get_raw_ingest_processing_status(context_id)
        processing_status = dict(processing_status or {})
        processing_status.update(
            {
                "ocr_required": False,
                "ocr_completed": True,
                "ocr_completed_at": utc_now_iso(),
            }
        )

        ocr_payload = {
            "asset_type": asset_type,
            "storage_path": storage_path,
            "text": text,
            "backend": backend_name,
            "processed_at": processed_at_iso,
        }

        self.repo.update_raw_ingest_ocr(context_id, processing_status=processing_status, ocr=ocr_payload)

        self.repo.update_ocr_queue(
            queue_doc_id,
            {
                "status": "completed",
                "completed_at": utc_now_iso(),
                "result": {
                    "text_length": len(text),
                    "backend": backend_name,
                    "processed_at": processed_at_iso,
                },
            },
        )

        logger.info("✓ OCR completed for %s (%s)", queue_doc_id, asset_type)
        return result

    def fail_queue_entry(self, queue_doc_id: str, error: str) -> None:
        self.repo.update_ocr_queue(
            queue_doc_id,
            {
                "status": "failed",
                "last_error": error,
                "failed_at": utc_now_iso(),
            },
        )

    def process_pending(self, limit: int = 5) -> Dict[str, int]:
        """Process up to N pending OCR tasks.

        This method queries Supabase in production. For unit tests, prefer
        calling `process_queue_entry()` directly with fakes.
        """
        stats = {"processed": 0, "completed": 0, "failed": 0}

        for entry in self.repo.select_pending_ocr(limit=limit):
            stats["processed"] += 1
            try:
                queue_id = entry.get("id")
                if not queue_id:
                    raise ValueError("ocr_queue row missing id")
                self.process_queue_entry(queue_id, entry)
                stats["completed"] += 1
            except Exception as e:
                if entry.get("id"):
                    self.fail_queue_entry(entry["id"], str(e))
                stats["failed"] += 1

        return stats
