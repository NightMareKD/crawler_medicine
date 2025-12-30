"""
Scheduled Crawling Automation

Automates the crawling and annotation pipeline:
- Runs ingestion every 12 hours
- Runs bias audit weekly
- Monitors queue health
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scheduler.log')
    ]
)


class IngestionScheduler:
    """
    Schedules and runs ingestion tasks.
    """
    
    def __init__(
        self,
        crawl_interval_hours: float = 12.0,
        bias_audit_day: int = 6,  # Sunday (0=Monday, 6=Sunday)
        batch_size: int = 10
    ):
        """
        Initialize the scheduler.
        
        Args:
            crawl_interval_hours: Hours between crawl runs
            bias_audit_day: Day of week for bias audit (0-6)
            batch_size: URLs to process per batch
        """
        self.crawl_interval_hours = crawl_interval_hours
        self.bias_audit_day = bias_audit_day
        self.batch_size = batch_size
        
        self._running = False
        self._last_crawl: Optional[datetime] = None
        self._last_bias_audit: Optional[datetime] = None
    
    async def run_crawl_cycle(self):
        """Run a single crawl and annotation cycle."""
        logger.info("Starting crawl cycle...")
        
        try:
            from run_ingestion import IngestionOrchestrator
            from corpus.annotation_processor import AnnotationProcessor
            from ingestion.supabase_repo import SupabaseRepo
            
            # Initialize components
            orchestrator = IngestionOrchestrator(
                rate_limit_delay=3.0,
                max_concurrent=3
            )
            
            annotator = AnnotationProcessor()
            repo = SupabaseRepo.from_env()
            
            # Process queue
            results = await orchestrator.process_queue(batch_size=self.batch_size)
            
            logger.info(f"Crawl results: {results['successful']}/{results['processed']} successful")
            
            # Annotate new content
            for detail in results.get('details', []):
                if detail.get('status') == 'success':
                    context_id = detail.get('context_id')
                    if context_id:
                        try:
                            # Fetch content
                            doc = repo.get_raw_ingest(context_id)
                            if doc and doc.get('content'):
                                content = doc['content']
                                text = content.get('markdown', '') or content.get('cleaned_html', '')
                                
                                if text:
                                    # Run annotation
                                    result = annotator.process(
                                        text=text,
                                        context_id=context_id,
                                        source_url=doc.get('url')
                                    )
                                    
                                    # Save annotations
                                    annotator.save_to_supabase(result, repo)
                                    
                        except Exception as e:
                            logger.error(f"Annotation error for {context_id}: {e}")
            
            # Process OCR queue
            ocr_results = orchestrator.process_ocr_queue(limit=5)
            logger.info(f"OCR results: {ocr_results}")
            
            self._last_crawl = datetime.now(timezone.utc)
            
        except Exception as e:
            logger.error(f"Crawl cycle error: {e}")
    
    async def run_bias_audit(self):
        """Run weekly bias audit."""
        logger.info("Running bias audit...")
        
        try:
            from corpus.bias_auditor import BiasAuditor
            from ingestion.supabase_repo import SupabaseRepo
            
            repo = SupabaseRepo.from_env()
            auditor = BiasAuditor(repo)
            
            # Calculate distribution
            report = auditor.calculate_distribution()
            
            # Save report
            auditor.save_report(report, repo)
            
            # Generate markdown report
            markdown = auditor.generate_markdown_report(report)
            logger.info(f"Bias Report:\n{markdown}")
            
            # Log alerts
            for alert in report.alerts:
                if alert.severity in ('high', 'critical'):
                    logger.warning(f"BIAS ALERT: {alert.message}")
            
            self._last_bias_audit = datetime.now(timezone.utc)
            
        except Exception as e:
            logger.error(f"Bias audit error: {e}")
    
    def should_run_crawl(self) -> bool:
        """Check if crawl should run."""
        if self._last_crawl is None:
            return True
        
        elapsed = datetime.now(timezone.utc) - self._last_crawl
        return elapsed.total_seconds() >= (self.crawl_interval_hours * 3600)
    
    def should_run_bias_audit(self) -> bool:
        """Check if bias audit should run."""
        now = datetime.now(timezone.utc)
        
        # Run on specified day
        if now.weekday() != self.bias_audit_day:
            return False
        
        # Only run once per day
        if self._last_bias_audit:
            elapsed = now - self._last_bias_audit
            if elapsed.total_seconds() < 86400:  # 24 hours
                return False
        
        return True
    
    async def start(self):
        """Start the scheduler loop."""
        logger.info("Starting ingestion scheduler...")
        logger.info(f"  Crawl interval: {self.crawl_interval_hours} hours")
        logger.info(f"  Bias audit day: {self.bias_audit_day}")
        
        self._running = True
        
        while self._running:
            try:
                # Check if crawl needed
                if self.should_run_crawl():
                    await self.run_crawl_cycle()
                
                # Check if bias audit needed
                if self.should_run_bias_audit():
                    await self.run_bias_audit()
                
                # Sleep for 5 minutes between checks
                await asyncio.sleep(300)
                
            except KeyboardInterrupt:
                logger.info("Scheduler interrupted by user")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    def stop(self):
        """Stop the scheduler."""
        self._running = False
        logger.info("Scheduler stopped")


async def main():
    """Main entry point for scheduler."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Ingestion Scheduler")
    parser.add_argument(
        "--interval", type=float, default=12.0,
        help="Hours between crawl cycles (default: 12)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="URLs per batch (default: 10)"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run once and exit"
    )
    
    args = parser.parse_args()
    
    scheduler = IngestionScheduler(
        crawl_interval_hours=args.interval,
        batch_size=args.batch_size
    )
    
    if args.once:
        await scheduler.run_crawl_cycle()
    else:
        await scheduler.start()


if __name__ == "__main__":
    print("=" * 60)
    print("  MULTILINGUAL HEALTH CORPUS SCHEDULER")
    print("  Automated Crawling & Annotation Pipeline")
    print("=" * 60)
    print()
    
    asyncio.run(main())
