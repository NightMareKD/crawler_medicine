"""
URL Manager
Manages crawl queue with priority scoring and scheduling
"""

import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import logging

from ingestion.supabase_repo import SupabaseRepo, utc_now_iso

logger = logging.getLogger(__name__)


class URLManager:
    """
    Manages URL crawl queue with intelligent prioritization
    """
    
    # Priority weights
    PRIORITY_WEIGHTS = {
        'critical': 1.0,
        'high': 0.8,
        'medium': 0.5,
        'low': 0.3
    }
    
    # Source reliability scores
    SOURCE_RELIABILITY = {
        'epid.gov.lk': 0.95,
        'health.gov.lk': 0.95,
        'moh.gov.lk': 0.90,
        'gov.lk': 0.85,
        'other': 0.70
    }
    
    def __init__(self, repo: Optional[SupabaseRepo] = None):
        """Initialize URL manager."""
        self.repo = repo or SupabaseRepo.from_env()
        logger.info("URLManager initialized")

    @staticmethod
    def _to_utc_iso(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    
    def calculate_priority_score(
        self,
        url: str,
        source_reliability: Optional[float] = None,
        priority_level: str = 'medium',
        freshness_days: int = 0,
        user_demand: float = 0.0
    ) -> float:
        """
        Calculate priority score for URL
        
        Args:
            url: URL to score
            source_reliability: Reliability score (0-1)
            priority_level: Priority level ('critical', 'high', 'medium', 'low')
            freshness_days: Days since last crawl
            user_demand: User demand score (0-1)
            
        Returns:
            Priority score (0-1)
        """
        # Base priority from level
        base_score = self.PRIORITY_WEIGHTS.get(priority_level, 0.5)
        
        # Source reliability
        domain = urlparse(url).netloc
        if source_reliability is None:
            for source, reliability in self.SOURCE_RELIABILITY.items():
                if source in domain:
                    source_reliability = reliability
                    break
            else:
                source_reliability = 0.70
        
        # Freshness bonus (older content gets higher priority for refresh)
        freshness_score = min(freshness_days / 30.0, 1.0) * 0.3
        
        # User demand
        demand_score = user_demand * 0.2
        
        # Calculate final score
        final_score = (
            base_score * 0.4 +
            source_reliability * 0.3 +
            freshness_score +
            demand_score
        )
        
        return min(max(final_score, 0.0), 1.0)
    
    def add_url(
        self,
        url: str,
        source_config: Dict[str, Any],
        priority: str = 'medium',
        scheduled_time: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Add URL to crawl queue
        
        Args:
            url: URL to add
            source_config: Source configuration metadata
            priority: Priority level
            scheduled_time: When to crawl (None for immediate)
            
        Returns:
            Queue entry document ID or None if already exists
        """
        # Calculate priority score
        priority_score = self.calculate_priority_score(
            url=url,
            source_reliability=source_config.get('reliability'),
            priority_level=priority,
            freshness_days=0,
            user_demand=source_config.get('user_demand', 0.0)
        )
        
        queue_entry = {
            'url': url,
            'domain': urlparse(url).netloc,
            'source_agency': source_config.get('agency', 'Unknown'),
            'priority': priority,
            'priority_score': priority_score,
            'status': 'pending',
            'scheduled_time': self._to_utc_iso(scheduled_time or datetime.utcnow()),
            'created_at': utc_now_iso(),
            'attempts': 0,
            'max_attempts': 3,
            'last_error': None,
            'metadata': source_config
        }
        
        # Check if URL already exists
        if self.repo.crawl_queue_exists_pending(url):
            logger.info(f"URL already in queue: {url}")
            return None
        
        queue_id = self.repo.insert_crawl_queue(queue_entry)
        
        logger.info(f"✓ Added to queue: {url} (score: {priority_score:.2f})")
        return queue_id
    
    def add_url_batch(
        self,
        urls: List[str],
        source_config: Dict[str, Any],
        priority: str = 'medium'
    ) -> List[str]:
        """
        Add multiple URLs to queue
        
        Args:
            urls: List of URLs
            source_config: Source configuration
            priority: Priority level
            
        Returns:
            List of created document IDs
        """
        doc_ids = []
        
        for url in urls:
            priority_score = self.calculate_priority_score(
                url=url,
                priority_level=priority
            )
            
            queue_entry = {
                'url': url,
                'domain': urlparse(url).netloc,
                'source_agency': source_config.get('agency', 'Unknown'),
                'priority': priority,
                'priority_score': priority_score,
                'status': 'pending',
                'scheduled_time': self._to_utc_iso(datetime.utcnow()),
                'created_at': utc_now_iso(),
                'attempts': 0,
                'max_attempts': 3,
                'metadata': source_config
            }

            doc_ids.append(self.repo.insert_crawl_queue(queue_entry))
        
        logger.info(f"✓ Added {len(urls)} URLs to queue")
        return doc_ids
    
    def get_next_urls(
        self,
        limit: int = 10,
        domain_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get next URLs to crawl based on priority
        
        Args:
            limit: Maximum URLs to return
            domain_filter: Filter by specific domain
            
        Returns:
            List of queue entries
        """
        rows = self.repo.select_next_crawl_queue(limit=limit, now_iso=utc_now_iso(), domain=domain_filter)

        urls = []
        for row in rows:
            data = dict(row)
            data['doc_id'] = data.get('id')
            urls.append(data)
        
        logger.info(f"Retrieved {len(urls)} URLs from queue")
        return urls
    
    def mark_processing(self, doc_id: str) -> bool:
        """
        Mark URL as being processed
        
        Args:
            doc_id: Queue document ID
            
        Returns:
            True if successful
        """
        try:
            # best-effort attempt increment
            current = self.repo.supabase.table('crawl_queue').select('attempts').eq('id', doc_id).limit(1).execute()
            attempts = 0
            data = getattr(current, 'data', None) or []
            if data and isinstance(data, list):
                attempts = int(data[0].get('attempts') or 0)

            self.repo.update_crawl_queue(
                doc_id,
                {
                    'status': 'processing',
                    'processing_started_at': utc_now_iso(),
                    'attempts': attempts + 1,
                },
            )
            return True
        except Exception as e:
            logger.error(f"Failed to mark processing: {str(e)}")
            return False
    
    def mark_completed(self, doc_id: str, context_id: str) -> bool:
        """
        Mark URL as successfully crawled
        
        Args:
            doc_id: Queue document ID
            context_id: Associated raw_ingest document ID
            
        Returns:
            True if successful
        """
        try:
            self.repo.update_crawl_queue(
                doc_id,
                {
                    'status': 'completed',
                    'completed_at': utc_now_iso(),
                    'context_id': context_id,
                },
            )
            logger.info(f"✓ Marked completed: {doc_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to mark completed: {str(e)}")
            return False
    
    def mark_failed(
        self,
        doc_id: str,
        error_message: str,
        retry: bool = True
    ) -> bool:
        """
        Mark URL as failed
        
        Args:
            doc_id: Queue document ID
            error_message: Error description
            retry: Whether to retry later
            
        Returns:
            True if successful
        """
        try:
            current = self.repo.supabase.table('crawl_queue').select('attempts,max_attempts').eq('id', doc_id).limit(1).execute()
            rows = getattr(current, 'data', None) or []
            if not rows:
                return False
            row = rows[0]
            attempts = int(row.get('attempts') or 0) + 1
            max_attempts = int(row.get('max_attempts') or 3)
            
            update_data = {
                'attempts': attempts,
                'last_error': error_message,
                'last_attempt_at': utc_now_iso(),
            }
            
            if retry and attempts < max_attempts:
                # Exponential backoff for retry
                retry_delay = timedelta(minutes=2 ** attempts)
                update_data['status'] = 'pending'
                update_data['scheduled_time'] = self._to_utc_iso(datetime.utcnow() + retry_delay)
                logger.info(f"Retrying {doc_id} in {retry_delay}")
            else:
                update_data['status'] = 'failed'
                logger.error(f"Failed permanently: {doc_id}")

            self.repo.update_crawl_queue(doc_id, update_data)
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark failed: {str(e)}")
            return False
    
    def get_queue_statistics(self) -> Dict[str, int]:
        """
        Get queue statistics
        
        Returns:
            Dict with status counts
        """
        stats = {
            'pending': 0,
            'processing': 0,
            'completed': 0,
            'failed': 0,
            'total': 0
        }
        
        try:
            for status in ['pending', 'processing', 'completed', 'failed']:
                resp = self.repo.supabase.table('crawl_queue').select('id', count='exact').eq('status', status).execute()
                count_val = getattr(resp, 'count', None)
                if count_val is None:
                    data = getattr(resp, 'data', None) or []
                    count_val = len(data)
                stats[status] = int(count_val)
                stats['total'] += int(count_val)
            
            logger.info(f"Queue stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {str(e)}")
            return stats
    
    def clean_old_entries(self, days: int = 30) -> int:
        """
        Clean old completed/failed entries
        
        Args:
            days: Age threshold in days
            
        Returns:
            Number of entries deleted
        """
        cutoff = self._to_utc_iso(datetime.utcnow() - timedelta(days=days))

        # Fetch candidates (best-effort). If you need large-scale deletion, use SQL.
        resp = (
            self.repo.supabase.table('crawl_queue')
            .select('id')
            .in_('status', ['completed', 'failed'])
            .lt('completed_at', cutoff)
            .limit(1000)
            .execute()
        )
        rows = list(getattr(resp, 'data', None) or [])
        deleted = 0
        for row in rows:
            self.repo.supabase.table('crawl_queue').delete().eq('id', row['id']).execute()
            deleted += 1

        logger.info(f"Cleaned {deleted} old entries")
        return deleted


# Example usage
def main():
    """Example usage"""
    manager = URLManager()
    
    # Add URL
    doc_id = manager.add_url(
        url='http://www.epid.gov.lk/disease-reports/dengue',
        source_config={
            'agency': 'Epidemiology Unit',
            'reliability': 0.95,
            'user_demand': 0.8
        },
        priority='high'
    )
    
    print(f"Added URL: {doc_id}")
    
    # Get statistics
    stats = manager.get_queue_statistics()
    print(f"Queue stats: {stats}")


if __name__ == "__main__":
    main()
