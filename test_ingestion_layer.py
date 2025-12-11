"""
Test Script for Data Ingestion Layer
Tests crawler, asset segregator, and URL manager
"""

import asyncio
import sys
from pathlib import Path

# Test with emulator or real Firebase
USE_EMULATOR = False  # Set to False to use real Firebase


async def test_url_manager():
    """Test URL queue management"""
    print("\n" + "="*60)
    print("TEST 1: URL Manager")
    print("="*60)
    
    from ingestion.url_manager import URLManager
    
    manager = URLManager()
    
    # Add test URLs
    print("\n1. Adding URLs to queue...")
    test_urls = [
        {
            'url': 'http://www.epid.gov.lk/',
            'priority': 'high',
            'source_config': {
                'agency': 'Epidemiology Unit',
                'reliability': 0.95
            }
        },
        {
            'url': 'http://www.health.gov.lk/',
            'priority': 'high',
            'source_config': {
                'agency': 'Ministry of Health',
                'reliability': 0.95
            }
        },
        {
            'url': 'http://www.epid.gov.lk/web/index.php?option=com_content&view=article&id=148',
            'priority': 'medium',
            'source_config': {
                'agency': 'Epidemiology Unit',
                'reliability': 0.95
            }
        }
    ]
    
    doc_ids = []
    for url_data in test_urls:
        doc_id = manager.add_url(**url_data)
        doc_ids.append(doc_id)
        print(f"   ✓ Added: {url_data['url'][:60]}... [{url_data['priority']}]")
    
    # Get queue statistics
    print("\n2. Queue Statistics:")
    stats = manager.get_queue_statistics()
    print(f"   Total: {stats.get('total', 0)} URLs")
    print(f"   Pending: {stats.get('pending', 0)}")
    print(f"   Completed: {stats.get('completed', 0)}")
    
    # Get next URLs
    print("\n3. Getting next URLs to crawl:")
    next_urls = manager.get_next_urls(limit=3)
    for entry in next_urls:
        print(f"   → {entry['url'][:60]}... (score: {entry.get('priority_score', 0):.3f})")
    
    print("\n✓ URL Manager test complete")
    return doc_ids


async def test_crawler():
    """Test web crawler with a simple page"""
    print("\n" + "="*60)
    print("TEST 2: Web Crawler")
    print("="*60)
    
    from ingestion.crawler_agent import AdaptiveCrawlerAgent
    
    crawler = AdaptiveCrawlerAgent(rate_limit_delay=1.0)
    
    # Test with a simple, reliable URL
    test_url = 'http://www.epid.gov.lk/'
    
    print(f"\n1. Crawling: {test_url}")
    print("   (This may take 10-30 seconds...)")
    
    try:
        result = await crawler.crawl(
            url=test_url,
            source_config={
                'agency': 'Epidemiology Unit',
                'reliability': 0.95
            },
            extraction_strategy='css'
        )
        
        if result.get('success', False):
            print(f"   ✓ Crawl successful!")
            print(f"   Context ID: {result.get('context_id')}")
            
            content = result.get('content', {})
            metadata = result.get('metadata', {})
            print(f"   Title: {metadata.get('title', 'N/A')[:60]}")
            print(f"   Markdown Length: {len(content.get('markdown', ''))} chars")
            print(f"   Links Found: {len(content.get('links', {}).get('internal', []))}")
            print(f"   Media Found: {len(content.get('media', {}).get('images', []))}")
            
            return result
        else:
            print(f"   ✗ Crawl failed: {result.get('error')}")
            return None
            
    except Exception as e:
        print(f"   ✗ Error: {str(e)}")
        return None


async def test_asset_segregator(crawl_result):
    """Test asset segregation"""
    print("\n" + "="*60)
    print("TEST 3: Asset Segregator")
    print("="*60)
    
    if not crawl_result:
        print("   ⚠ Skipping (no crawl result)")
        return
    
    from ingestion.asset_segregator import AssetSegregator
    
    segregator = AssetSegregator()
    
    print("\n1. Segregating assets from crawled content...")
    result = segregator.segregate_from_context(crawl_result)
    
    assets = result.get('assets', {})
    counts = result.get('asset_counts', {})
    
    print(f"   ✓ Segregation complete")
    print(f"\n2. Asset Counts:")
    print(f"   HTML Links: {counts.get('html', 0)}")
    print(f"   PDF Links: {counts.get('pdf', 0)}")
    print(f"   Images: {counts.get('image', 0)}")
    print(f"   Other Docs: {counts.get('document', 0)}")
    
    # Show sample assets
    if assets.get('pdf_links'):
        print(f"\n3. Sample PDF found:")
        pdf = assets['pdf_links'][0]
        print(f"   {pdf['url'][:80]}")
    
    if assets.get('images'):
        print(f"\n4. Sample Images:")
        for img in assets['images'][:3]:
            print(f"   {img['src'][:80]}")
    
    print("\n✓ Asset segregator test complete")


async def test_orchestrator():
    """Test the full orchestrator"""
    print("\n" + "="*60)
    print("TEST 4: Ingestion Orchestrator")
    print("="*60)
    
    from run_ingestion import IngestionOrchestrator
    
    orchestrator = IngestionOrchestrator(
        rate_limit_delay=2.0,
        max_concurrent=2
    )
    
    print("\n1. System Status:")
    status = orchestrator.get_system_status()
    print(f"   Queue: {status['queue']}")
    
    print("\n2. Processing queue (1 URL)...")
    print("   (This may take 10-30 seconds...)")
    
    try:
        results = await orchestrator.process_queue(batch_size=1)
        print(f"   ✓ Processed: {results['successful']}/{results['processed']} successful")
        
        if results['details']:
            detail = results['details'][0]
            print(f"   URL: {detail['url'][:60]}")
            print(f"   Status: {detail['status']}")
            if detail.get('assets'):
                print(f"   Assets: {detail['assets']}")
    
    except Exception as e:
        print(f"   ✗ Error: {str(e)}")
    
    print("\n✓ Orchestrator test complete")


async def main():
    """Run all tests"""
    
    print("="*60)
    print("  CRAWL4AI DATA INGESTION LAYER - TEST SUITE")
    print("="*60)
    
    # Setup Firebase
    print("\nInitializing Firebase...")
    
    if USE_EMULATOR:
        print("⚠ Using Firebase EMULATOR (no real cloud access)")
        print("  Start emulator first: firebase emulators:start")
        print("\n✗ ERROR: Emulator not implemented yet!")
        print("\nPlease set USE_EMULATOR = False in test_ingestion_layer.py")
        print("The test will use your real Firebase credentials.")
        return
    else:
        print("✓ Using REAL Firebase (cloud access)")
        # Check if credentials exist
        creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not creds_path or not Path(creds_path).exists():
            print("\n✗ ERROR: Firebase credentials not found!")
            print("\nSetup instructions:")
            print("1. Create .env file from .env.example")
            print("2. Download service account key from Firebase Console")
            print("3. Update GOOGLE_APPLICATION_CREDENTIALS in .env")
            print("\nOr set USE_EMULATOR = True to test locally")
            return
    
    try:
        # Initialize Firebase
        from firebase_admin_setup import init_firebase
        init_firebase()
        print("✓ Firebase initialized")
        
        # Run tests
        doc_ids = await test_url_manager()
        await asyncio.sleep(1)
        
        crawl_result = await test_crawler()
        await asyncio.sleep(1)
        
        await test_asset_segregator(crawl_result)
        await asyncio.sleep(1)
        
        await test_orchestrator()
        
        print("\n" + "="*60)
        print("  ALL TESTS COMPLETE")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import os
    import json
    from dotenv import load_dotenv
    
    # Load environment variables
    load_dotenv()
    
    asyncio.run(main())
