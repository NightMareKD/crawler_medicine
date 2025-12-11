"""
Ingestion Layer Orchestrator
Coordinates crawler, asset segregation, and queue management
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from ingestion.crawler_agent import AdaptiveCrawlerAgent
from ingestion.asset_segregator import AssetSegregator
from ingestion.url_manager import URLManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    """
    Orchestrates the complete ingestion pipeline
    """
    
    def __init__(
        self,
        rate_limit_delay: float = 2.0,
        max_concurrent: int = 3
    ):
        """
        Initialize orchestrator
        
        Args:
            rate_limit_delay: Delay between requests to same domain
            max_concurrent: Maximum concurrent crawls
        """
        self.crawler = AdaptiveCrawlerAgent(rate_limit_delay=rate_limit_delay)
        self.segregator = AssetSegregator()
        self.url_manager = URLManager()
        self.max_concurrent = max_concurrent
        
        logger.info("IngestionOrchestrator initialized")
    
    async def process_queue(
        self,
        batch_size: int = 10,
        domain_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process URLs from the crawl queue
        
        Args:
            batch_size: Number of URLs to process
            domain_filter: Filter by specific domain
            
        Returns:
            Processing results summary
        """
        # Get next URLs from queue
        queue_entries = self.url_manager.get_next_urls(
            limit=batch_size,
            domain_filter=domain_filter
        )
        
        if not queue_entries:
            logger.info("No URLs in queue")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        logger.info(f"Processing {len(queue_entries)} URLs from queue")
        
        results = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'details': []
        }
        
        for entry in queue_entries:
            doc_id = entry['doc_id']
            url = entry['url']
            
            # Mark as processing
            self.url_manager.mark_processing(doc_id)
            
            try:
                # Crawl the URL
                result = await self.crawler.crawl(
                    url=url,
                    source_config=entry.get('metadata', {}),
                    extraction_strategy='css'
                )
                
                results['processed'] += 1
                
                if result.get('success', False):
                    context_id = result.get('context_id')
                    
                    if not context_id:
                        logger.error(f"No context_id in result: {result}")
                        # Mark as failed
                        error = "No context_id returned from crawler"
                        self.url_manager.mark_failed(doc_id, error, retry=True)
                        results['failed'] += 1
                        results['details'].append({
                            'url': url,
                            'status': 'failed',
                            'error': error
                        })
                        continue
                    
                    # Segregate assets
                    result = self.segregator.segregate_from_context(result)
                    
                    # Update Firestore with segregation data
                    from firebase_admin_setup import get_db
                    db = get_db()
                    try:
                        db.collection('raw_ingest').document(context_id).update({
                            'assets': result.get('assets', {}),
                            'asset_counts': result.get('asset_counts', {})
                        })
                    except Exception as e:
                        logger.warning(f"Could not update assets in Firestore: {e}")
                    
                    # Mark queue entry as completed
                    self.url_manager.mark_completed(doc_id, context_id)
                    
                    results['successful'] += 1
                    results['details'].append({
                        'url': url,
                        'status': 'success',
                        'context_id': context_id,
                        'assets': result.get('asset_counts', {})
                    })
                    
                    # Download and queue PDFs for OCR
                    await self._process_assets(result, context_id)
                    
                else:
                    # Mark as failed
                    error = result.get('error', 'Unknown error')
                    self.url_manager.mark_failed(doc_id, error, retry=True)
                    results['failed'] += 1
                    results['details'].append({
                        'url': url,
                        'status': 'failed',
                        'error': error
                    })
            
            except Exception as e:
                logger.error(f"Error processing {url}: {str(e)}")
                self.url_manager.mark_failed(doc_id, str(e), retry=True)
                results['failed'] += 1
                results['details'].append({
                    'url': url,
                    'status': 'error',
                    'error': str(e)
                })
        
        logger.info(
            f"Batch complete: {results['successful']}/{results['processed']} successful"
        )
        return results
    
    async def _process_assets(
        self,
        context_obj: Dict[str, Any],
        context_id: str
    ):
        """
        Download and queue assets for processing
        
        Args:
            context_obj: Context object with assets
            context_id: Context document ID
        """
        assets = context_obj.get('assets', {})
        
        # Process PDFs
        for pdf in assets.get('pdf_links', [])[:5]:  # Limit to 5 PDFs per page
            if pdf.get('needs_download', False):
                try:
                    storage_path = await self.segregator.download_and_store_asset(
                        url=pdf['url'],
                        asset_type='pdf',
                        context_id=context_id
                    )
                    
                    if storage_path and pdf.get('needs_ocr', False):
                        # Create OCR queue entry
                        self.segregator.create_ocr_queue_entry(
                            storage_path=storage_path,
                            context_id=context_id,
                            asset_type='pdf',
                            priority=pdf.get('priority', 'medium')
                        )
                except Exception as e:
                    logger.error(f"Failed to process PDF {pdf['url']}: {str(e)}")
    
    async def crawl_seed_urls(
        self,
        seed_urls: List[str],
        source_config: Dict[str, Any]
    ) -> List[str]:
        """
        Crawl seed URLs and discover more URLs
        
        Args:
            seed_urls: Initial URLs to crawl
            source_config: Source configuration
            
        Returns:
            List of discovered URLs
        """
        discovered_urls = []
        
        for url in seed_urls:
            try:
                # Crawl seed URL
                result = await self.crawler.crawl(
                    url=url,
                    source_config=source_config,
                    extraction_strategy='css'
                )
                
                if result.get('success', False):
                    # Extract and score links
                    content = result.get('content', {})
                    links = content.get('links', {})
                    
                    for link in links.get('internal', []):
                        # Score link relevance
                        score = self.crawler.score_link_relevance(
                            url=link,
                            text=''  # Could extract anchor text
                        )
                        
                        if score > 0.5:  # Only queue relevant links
                            discovered_urls.append(link)
                            
                            # Add to queue
                            self.url_manager.add_url(
                                url=link,
                                source_config=source_config,
                                priority='high' if score > 0.8 else 'medium'
                            )
                
            except Exception as e:
                logger.error(f"Error crawling seed URL {url}: {str(e)}")
        
        logger.info(f"Discovered {len(discovered_urls)} URLs from seed crawl")
        return discovered_urls
    
    def get_system_status(self) -> Dict[str, Any]:
        """
        Get overall ingestion system status
        
        Returns:
            Status summary
        """
        queue_stats = self.url_manager.get_queue_statistics()
        asset_stats = self.segregator.get_statistics()
        
        status = {
            'queue': queue_stats,
            'assets': asset_stats,
            'timestamp': asyncio.get_event_loop().time()
        }
        
        return status


# Example usage and main entry point
async def main():
    """
    Example ingestion pipeline execution
    """
    # Initialize orchestrator
    orchestrator = IngestionOrchestrator(
        rate_limit_delay=3.0,
        max_concurrent=3
    )
    
    # Example 1: Crawl seed URLs (initial discovery)
    logger.info("=== STEP 1: Seed URL Crawling ===")
    seed_urls = [
        'http://www.epid.gov.lk/',
        'http://www.health.gov.lk/',
    ]
    
    source_config = {
        'agency': 'Epidemiology Unit',
        'reliability': 0.95,
        'user_demand': 0.9
    }
    
    discovered = await orchestrator.crawl_seed_urls(seed_urls, source_config)
    print(f"✓ Discovered {len(discovered)} URLs")
    
    # Example 2: Process queue
    logger.info("\n=== STEP 2: Processing Queue ===")
    results = await orchestrator.process_queue(batch_size=5)
    print(f"✓ Processed: {results['successful']}/{results['processed']} successful")
    
    # Example 3: Get system status
    logger.info("\n=== STEP 3: System Status ===")
    status = orchestrator.get_system_status()
    print(f"Queue Status: {status['queue']}")
    print(f"Asset Stats: {status['assets']}")
    
    # Example 4: Manual URL addition
    logger.info("\n=== STEP 4: Manual URL Addition ===")
    url_manager = URLManager()
    doc_id = url_manager.add_url(
        url='http://www.epid.gov.lk/web/index.php?option=com_content&view=article&id=148',
        source_config={
            'agency': 'Epidemiology Unit',
            'reliability': 0.95
        },
        priority='high'
    )
    print(f"✓ Added URL to queue: {doc_id}")


if __name__ == "__main__":
    print("=" * 60)
    print("  CRAWL4AI DATA INGESTION LAYER")
    print("  Layer 1: Web Crawling, Asset Segregation, Queue Management")
    print("=" * 60)
    print()
    
    try:
        asyncio.run(main())
        print("\n✓ Ingestion pipeline completed successfully")
    except KeyboardInterrupt:
        print("\n⚠ Interrupted by user")
    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        import traceback
        traceback.print_exc()
