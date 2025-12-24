"""Run OCR worker.

Pulls pending items from Supabase `ocr_queue`, downloads assets from Supabase Storage,
and writes extracted text back to `raw_ingest`.

Usage (PowerShell):
    $env:SUPABASE_URL='https://YOUR_PROJECT.supabase.co'
    $env:SUPABASE_SERVICE_ROLE_KEY='YOUR_SERVICE_ROLE_KEY'
    $env:SUPABASE_STORAGE_BUCKET='assets'
    python run_ocr.py
"""

import time
import logging

from ingestion.supabase_repo import SupabaseRepo
from ingestion.ocr_processor import OCRProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    processor = OCRProcessor(repo=SupabaseRepo.from_env())

    logger.info("Starting OCR worker")
    while True:
        stats = processor.process_pending(limit=5)
        logger.info("OCR batch: %s", stats)

        # Sleep when idle
        if stats.get("processed", 0) == 0:
            time.sleep(10)
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
