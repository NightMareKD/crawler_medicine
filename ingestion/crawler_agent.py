"""
Adaptive Crawler Agent using Crawl4AI
Politely crawls government health websites with rate limiting and robots.txt respect
"""

import asyncio
import time
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import logging
from datetime import datetime

from crawl4ai import AsyncWebCrawler  # type: ignore
from crawl4ai.extraction_strategy import LLMExtractionStrategy, JsonCssExtractionStrategy  # type: ignore
from crawl4ai.chunking_strategy import RegexChunking  # type: ignore
from crawl4ai.async_configs import CacheMode  # type: ignore

from ingestion.supabase_repo import SupabaseRepo, utc_now_iso


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AdaptiveCrawlerAgent:
    """
    Adaptive web crawler with politeness policies and Supabase persistence
    """
    
    def __init__(
        self,
        rate_limit_delay: float = 2.0,
        max_retries: int = 3,
        respect_robots: bool = True,
        user_agent: str = "Crawl4AI-HealthBot/1.0 (+https://health.gov.lk)"
    ):
        """
        Initialize the crawler agent
        
        Args:
            rate_limit_delay: Delay between requests to same domain (seconds)
            max_retries: Maximum retry attempts for failed requests
            respect_robots: Whether to respect robots.txt
            user_agent: User agent string for requests
        """
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.respect_robots = respect_robots
        self.user_agent = user_agent
        
        # Domain-specific tracking for politeness
        self.domain_last_access: Dict[str, float] = {}
        self.robots_cache: Dict[str, RobotFileParser] = {}
        
        # Backend
        self.repo = SupabaseRepo.from_env()
        
        logger.info(f"Initialized AdaptiveCrawlerAgent with {rate_limit_delay}s rate limit")
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    def _can_fetch(self, url: str) -> bool:
        """
        Check if URL can be fetched according to robots.txt
        
        Args:
            url: URL to check
            
        Returns:
            True if URL can be fetched
        """
        if not self.respect_robots:
            return True
        
        domain = self._get_domain(url)
        
        # Check cache first
        if domain not in self.robots_cache:
            robots_url = urljoin(domain, '/robots.txt')
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                self.robots_cache[domain] = rp
            except Exception as e:
                logger.warning(f"Failed to read robots.txt for {domain}: {e}")
                # If robots.txt cannot be read, allow by default
                return True
        
        rp = self.robots_cache[domain]
        can_fetch = rp.can_fetch(self.user_agent, url)
        
        if not can_fetch:
            logger.warning(f"Blocked by robots.txt: {url}")
        
        return can_fetch
    
    async def _throttle(self, url: str):
        """
        Enforce rate limiting per domain
        
        Args:
            url: URL being accessed
        """
        domain = self._get_domain(url)
        
        if domain in self.domain_last_access:
            elapsed = time.time() - self.domain_last_access[domain]
            if elapsed < self.rate_limit_delay:
                sleep_time = self.rate_limit_delay - elapsed
                logger.info(f"Throttling {domain} for {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
        
        self.domain_last_access[domain] = time.time()
    
    async def crawl(
        self,
        url: str,
        source_config: Dict[str, Any],
        extraction_strategy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Crawl a single URL with context engineering
        
        Args:
            url: URL to crawl
            source_config: Configuration dict with metadata (agency, priority, etc.)
            extraction_strategy: Strategy to use ('llm', 'css', or None for default)
            
        Returns:
            Dict containing crawled data and metadata
        """
        # Check robots.txt
        if not self._can_fetch(url):
            return {
                'success': False,
                'error': 'Blocked by robots.txt',
                'url': url
            }
        
        # Enforce rate limiting
        await self._throttle(url)
        
        # Configure extraction strategy
        strategy = None
        if extraction_strategy == 'llm':
            strategy = LLMExtractionStrategy(
                provider="openai/gpt-4",
                api_token=None,  # Will use env variable
                instruction="Extract health-related content including: disease information, clinic schedules, health advisories, vaccination details, and contact information."
            )
        elif extraction_strategy == 'css':
            # Default CSS selectors for common government sites
            schema = {
                "name": "Health Content",
                "baseSelector": "body",
                "fields": [
                    {"name": "title", "selector": "h1, h2", "type": "text"},
                    {"name": "content", "selector": "p, article, .content", "type": "text"},
                    {"name": "date", "selector": ".date, time", "type": "text"},
                ]
            }
            strategy = JsonCssExtractionStrategy(schema)
        
        # Attempt crawl with retries
        for attempt in range(self.max_retries):
            try:
                async with AsyncWebCrawler(
                    verbose=True,
                    headless=True,
                    user_agent=self.user_agent
                ) as crawler:
                    result = await crawler.arun(
                        url=url,
                        extraction_strategy=strategy,
                        cache_mode=CacheMode.BYPASS,  # Always fetch fresh data
                        word_count_threshold=10,
                        chunking_strategy=RegexChunking(patterns=[r'\n\n'])
                    )
                    
                    if result.success:
                        # Build context object
                        context_obj = self._build_context_object(
                            result=result,
                            url=url,
                            source_config=source_config
                        )
                        
                        # Store in Supabase
                        await self._store_to_supabase(context_obj)
                        
                        logger.info(f"✓ Successfully crawled: {url}")
                        return context_obj
                    else:
                        logger.error(f"Crawl failed (attempt {attempt + 1}): {result.error_message}")
                        
            except Exception as e:
                logger.error(f"Exception on attempt {attempt + 1}: {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return {
            'success': False,
            'error': 'Max retries exceeded',
            'url': url
        }
    
    def _build_context_object(
        self,
        result: Any,
        url: str,
        source_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build Global Context Object with provenance and metadata
        
        Args:
            result: Crawl4AI result object
            url: Source URL
            source_config: Source configuration metadata
            
        Returns:
            Context object dict
        """
        # Generate document ID
        doc_id = self.repo.new_context_id()
        return {
            'success': True,
            'context_id': doc_id,
            '_doc_id': doc_id,  # Internal field for storage
            'url': url,
            'content': {
                'html': result.html[:50000] if result.html else '',  # Limit size
                'cleaned_html': result.cleaned_html[:50000] if result.cleaned_html else '',
                'markdown': result.markdown[:50000] if result.markdown else '',
                'extracted': result.extracted_content if hasattr(result, 'extracted_content') else None,
                'media': {
                    'images': [img['src'] for img in (result.media.get('images', []) if result.media else [])][:10],
                    'videos': [vid['src'] for vid in (result.media.get('videos', []) if result.media else [])][:5],
                },
                'links': {
                    'internal': [link['href'] for link in (result.links.get('internal', []) if result.links else [])][:20],
                    'external': [link['href'] for link in (result.links.get('external', []) if result.links else [])][:10],
                }
            },
            'provenance': {
                'source_agency': source_config.get('agency', 'Unknown'),
                'source_url': url,
                'ingest_timestamp': utc_now_iso(),
                'crawl_timestamp': datetime.utcnow().isoformat(),
                'original_format': 'HTML',
                'reliability_score': source_config.get('reliability', 0.9),
                'domain': self._get_domain(url),
                'crawler_version': 'Crawl4AI-v0.7.8',
            },
            'metadata': {
                'title': result.metadata.get('title', '') if result.metadata else '',
                'description': result.metadata.get('description', '') if result.metadata else '',
                'keywords': result.metadata.get('keywords', '') if result.metadata else '',
                'language': result.metadata.get('language', 'si') if result.metadata else 'si',
                'status_code': result.status_code,
                'success': result.success,
            },
            'processing_status': {
                'ocr_required': False,  # HTML content, no OCR needed
                'language_detected': False,
                'entities_extracted': False,
                'pii_scrubbed': False,
                'requires_human_review': False,
                'review_status': 'pending'
            },
            'priority': source_config.get('priority', 'medium'),
        }
    
    async def _store_to_supabase(self, context_obj: Dict[str, Any]) -> str:
        """
        Store crawled data to Supabase
        
        Args:
            context_obj: Context object to store
            
        Returns:
            Document ID
        """
        try:
            doc_id = context_obj.get('context_id')
            if not doc_id:
                raise ValueError('context_obj missing context_id')

            self.repo.upsert_raw_ingest(context_obj)
            self.repo.add_audit_log(
                event_type='crawl_completed',
                document_id=doc_id,
                url=context_obj.get('url'),
                success=bool(context_obj.get('metadata', {}).get('success')),
            )

            logger.info(f"✓ Stored to Supabase: {doc_id}")
            return doc_id
            
        except Exception as e:
            logger.error(f"Failed to store to Supabase: {str(e)}")
            raise
    
    async def crawl_batch(
        self,
        urls: List[str],
        source_config: Dict[str, Any],
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Crawl multiple URLs concurrently with rate limiting
        
        Args:
            urls: List of URLs to crawl
            source_config: Source configuration metadata
            max_concurrent: Maximum concurrent requests
            
        Returns:
            List of context objects
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def bounded_crawl(url: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.crawl(url, source_config)
        
        tasks = [bounded_crawl(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions
        successful_results = [
            r for r in results 
            if isinstance(r, dict) and r.get('success', False)
        ]
        
        logger.info(f"Batch complete: {len(successful_results)}/{len(urls)} successful")
        return successful_results
    
    def score_link_relevance(self, url: str, text: str) -> float:
        """
        Score link relevance using BM25 and keyword matching
        
        Args:
            url: URL to score
            text: Anchor text or surrounding text
            
        Returns:
            Relevance score (0.0 - 1.0)
        """
        # Health-related keywords (Sinhala, Tamil, English)
        keywords = [
            # English
            'clinic', 'hospital', 'disease', 'vaccine', 'health', 'medical',
            'dengue', 'leptospirosis', 'cholera', 'schedule', 'doctor',
            # Sinhala (romanized for URL matching)
            'auruwedaya', 'behethshalawa', 'roga', 'ennath',
            # Common URL patterns
            'pdf', 'circular', 'advisory', 'report', 'schedule'
        ]
        
        url_lower = url.lower()
        text_lower = text.lower()
        
        score = 0.0
        for keyword in keywords:
            if keyword in url_lower:
                score += 0.15
            if keyword in text_lower:
                score += 0.10
        
        # Boost government domains
        if 'gov.lk' in url_lower or 'health.gov.lk' in url_lower:
            score += 0.3
        
        # Penalize external links
        if url_lower.startswith('http') and 'gov.lk' not in url_lower:
            score -= 0.2
        
        return min(max(score, 0.0), 1.0)


# Example usage
async def main():
    """Example crawler usage"""
    crawler = AdaptiveCrawlerAgent(rate_limit_delay=3.0)
    
    # Example: Crawl Epidemiology Unit
    result = await crawler.crawl(
        url="http://www.epid.gov.lk/",
        source_config={
            'agency': 'Epidemiology Unit',
            'priority': 'high',
            'reliability': 0.95
        },
        extraction_strategy='css'
    )
    
    print(f"Crawl result: {result.get('success', False)}")


if __name__ == "__main__":
    asyncio.run(main())
