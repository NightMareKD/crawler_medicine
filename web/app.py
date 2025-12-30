"""
API & Dashboard Application

FastAPI application for:
- Corpus statistics dashboard
- Q&A pair review interface
- Annotation management API
- Bias report visualization
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Multilingual Health Corpus",
    description="Sri Lankan Health Corpus Management System",
    version="1.0.0"
)

# Setup templates
templates_dir = Path(__file__).parent / "templates"
templates_dir.mkdir(exist_ok=True)
templates = Jinja2Templates(directory=str(templates_dir))

# Lazy repo initialization
_repo = None

def get_repo():
    """Get or create SupabaseRepo instance."""
    global _repo
    if _repo is None:
        from ingestion.supabase_repo import SupabaseRepo
        _repo = SupabaseRepo.from_env()
    return _repo


# ========================================
# Dashboard Routes
# ========================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    try:
        repo = get_repo()
        
        # Get statistics
        stats = repo.get_latest_corpus_statistics()
        
        # Get recent Q&A pairs
        qa_pairs = repo.get_qa_pairs(limit=10)
        
        # Get queue status
        pending_resp = repo.supabase.table("crawl_queue").select(
            "id", count="exact"
        ).eq("status", "pending").execute()
        pending_count = getattr(pending_resp, "count", 0) or 0
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "stats": stats or {},
            "qa_pairs": qa_pairs,
            "pending_urls": pending_count
        })
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return HTMLResponse(f"<h1>Error loading dashboard</h1><p>{e}</p>")


@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    """Q&A review interface."""
    try:
        repo = get_repo()
        
        # Get unverified Q&A pairs
        qa_pairs = repo.get_qa_pairs(limit=50, verified_only=False)
        unverified = [qa for qa in qa_pairs if not qa.get("verified")]
        
        return templates.TemplateResponse("review.html", {
            "request": request,
            "qa_pairs": unverified
        })
    except Exception as e:
        logger.error(f"Review page error: {e}")
        return HTMLResponse(f"<h1>Error loading review page</h1><p>{e}</p>")


@app.get("/bias-report", response_class=HTMLResponse)
async def bias_report(request: Request):
    """Bias report visualization."""
    try:
        from corpus.bias_auditor import BiasAuditor
        repo = get_repo()
        
        auditor = BiasAuditor(repo)
        report = auditor.calculate_distribution()
        markdown = auditor.generate_markdown_report(report)
        
        return templates.TemplateResponse("bias_report.html", {
            "request": request,
            "report": report,
            "markdown": markdown
        })
    except Exception as e:
        logger.error(f"Bias report error: {e}")
        return HTMLResponse(f"<h1>Error generating report</h1><p>{e}</p>")


# ========================================
# API Routes
# ========================================

@app.get("/api/stats")
async def get_statistics():
    """Get corpus statistics."""
    try:
        repo = get_repo()
        stats = repo.get_latest_corpus_statistics()
        return stats or {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/qa-pairs")
async def get_qa_pairs(
    limit: int = 50,
    language: Optional[str] = None,
    domain: Optional[str] = None,
    verified_only: bool = False
):
    """Get Q&A pairs with filters."""
    try:
        repo = get_repo()
        pairs = repo.get_qa_pairs(
            limit=limit,
            language=language,
            domain=domain,
            verified_only=verified_only
        )
        return {"pairs": pairs, "count": len(pairs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/qa-pairs/{qa_id}/verify")
async def verify_qa_pair(qa_id: str, reviewer_id: str = "admin", notes: Optional[str] = None):
    """Verify a Q&A pair."""
    try:
        repo = get_repo()
        repo.verify_qa_pair(qa_id, reviewer_id, notes)
        return {"status": "success", "verified": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/documents/{context_id}")
async def get_document(context_id: str):
    """Get a document with its annotations."""
    try:
        repo = get_repo()
        doc = repo.get_raw_ingest(context_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotate")
async def annotate_text_api(text: str, source_url: Optional[str] = None):
    """Annotate text using the NLP pipeline."""
    try:
        from corpus.annotation_processor import AnnotationProcessor
        from uuid import uuid4
        
        processor = AnnotationProcessor()
        result = processor.process(
            text=text,
            context_id=str(uuid4()),
            source_url=source_url,
            generate_qa=True
        )
        
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bias-report")
async def get_bias_report():
    """Get current bias report."""
    try:
        from corpus.bias_auditor import BiasAuditor
        repo = get_repo()
        
        auditor = BiasAuditor(repo)
        report = auditor.calculate_distribution()
        
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/queue/add")
async def add_to_queue(url: str, priority: str = "medium"):
    """Add URL to crawl queue."""
    try:
        from ingestion.url_manager import URLManager
        
        manager = URLManager()
        queue_id = manager.add_url(
            url=url,
            source_config={"priority": priority, "agency": "api_submission"}
        )
        
        return {"status": "success", "queue_id": queue_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Health Check
# ========================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "multilingual-health-corpus"
    }


# ========================================
# Run Server
# ========================================

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Run the web server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Corpus Web Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  MULTILINGUAL HEALTH CORPUS - WEB INTERFACE")
    print(f"  Starting server at http://{args.host}:{args.port}")
    print("=" * 60)
    print()
    
    run_server(args.host, args.port)
