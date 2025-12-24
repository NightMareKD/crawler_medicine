"""
Asset Segregator
Separates HTML content from PDFs and images for appropriate processing
"""

from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
import logging
from pathlib import Path

from ingestion.supabase_repo import SupabaseRepo, utc_now_iso

logger = logging.getLogger(__name__)


class AssetSegregator:
    """
    Segregates different asset types (HTML, PDF, Images) for targeted processing
    """
    
    SUPPORTED_DOCUMENT_TYPES = {
        'pdf': ['.pdf'],
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'],
        'html': ['.html', '.htm'],
        'document': ['.doc', '.docx', '.txt', '.rtf']
    }
    
    def __init__(self, repo: Optional[SupabaseRepo] = None):
        """Initialize asset segregator."""
        self.repo = repo or SupabaseRepo.from_env()
        logger.info("AssetSegregator initialized")
    
    def detect_asset_type(self, url: str, content_type: Optional[str] = None) -> str:
        """
        Detect asset type from URL and content-type
        
        Args:
            url: URL or file path
            content_type: HTTP Content-Type header
            
        Returns:
            Asset type: 'pdf', 'image', 'html', 'document', 'unknown'
        """
        # Check content-type header first
        if content_type:
            if 'pdf' in content_type.lower():
                return 'pdf'
            elif 'image' in content_type.lower():
                return 'image'
            elif 'html' in content_type.lower():
                return 'html'
        
        # Check file extension
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        for asset_type, extensions in self.SUPPORTED_DOCUMENT_TYPES.items():
            if any(path.endswith(ext) for ext in extensions):
                return asset_type
        
        # Default to HTML if no extension
        if not Path(path).suffix:
            return 'html'
        
        return 'unknown'
    
    def segregate_from_context(self, context_obj: Dict[str, Any]) -> Dict[str, Any]:
        """
        Segregate assets from a crawled context object
        
        Args:
            context_obj: Context object from crawler
            
        Returns:
            Updated context object with segregation metadata
        """
        assets = {
            'html_content': [],
            'pdf_links': [],
            'image_links': [],
            'other_documents': []
        }
        
        # Process main content
        url = context_obj.get('url', '')
        asset_type = self.detect_asset_type(url)
        
        if asset_type == 'html':
            assets['html_content'].append({
                'url': url,
                'content': context_obj.get('content', {}),
                'needs_processing': False  # Already processed
            })
        
        # Extract links from content
        content = context_obj.get('content', {})
        links = content.get('links', {})
        
        # Process internal links
        for link in links.get('internal', []):
            link_type = self.detect_asset_type(link)
            
            if link_type == 'pdf':
                assets['pdf_links'].append({
                    'url': link,
                    'needs_download': True,
                    'needs_ocr': True,
                    'priority': context_obj.get('priority', 'medium')
                })
            elif link_type == 'image':
                assets['image_links'].append({
                    'url': link,
                    'needs_download': True,
                    'needs_ocr': True  # May contain text
                })
            elif link_type == 'document':
                assets['other_documents'].append({
                    'url': link,
                    'needs_download': True,
                    'needs_conversion': True
                })
        
        # Process media
        media = content.get('media', {})
        for img in media.get('images', []):
            if img not in assets['image_links']:
                assets['image_links'].append({
                    'url': img,
                    'needs_download': True,
                    'needs_ocr': False,  # Decorative images
                    'priority': 'low'
                })
        
        # Update context object
        context_obj['assets'] = assets
        context_obj['asset_counts'] = {
            'pdf': len(assets['pdf_links']),
            'images': len(assets['image_links']),
            'documents': len(assets['other_documents'])
        }
        
        # Mark if OCR processing is needed
        if assets['pdf_links'] or any(
            img.get('needs_ocr', False) for img in assets['image_links']
        ):
            context_obj['processing_status']['ocr_required'] = True
        
        logger.info(
            f"Segregated assets: {len(assets['pdf_links'])} PDFs, "
            f"{len(assets['image_links'])} images"
        )
        
        return context_obj
    
    async def download_and_store_asset(
        self,
        url: str,
        asset_type: str,
        context_id: str
    ) -> Optional[str]:
        """
        Download asset and store in Supabase Storage
        
        Args:
            url: Asset URL
            asset_type: Type of asset ('pdf', 'image', etc.)
            context_id: Associated context document ID
            
        Returns:
            Storage path or None if failed
        """
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                
                # Determine storage path
                file_ext = Path(urlparse(url).path).suffix or f'.{asset_type}'
                storage_path = f"{asset_type}s-raw/{context_id}/{Path(url).name}"
                
                content_type = response.headers.get('content-type', 'application/octet-stream')
                self.repo.upload_bytes(storage_path, response.content, content_type=content_type)
                
                logger.info(f"✓ Uploaded to storage: {storage_path}")
                
                # Update raw_ingest with storage reference (best-effort)
                try:
                    assets = self.repo.get_raw_ingest_assets(context_id)
                    downloaded = dict((assets or {}).get('downloaded') or {})
                    downloaded[asset_type] = {
                        'url': url,
                        'storage_path': storage_path,
                        'uploaded_at': utc_now_iso(),
                        'size_bytes': len(response.content),
                    }
                    merged_assets = dict(assets or {})
                    merged_assets['downloaded'] = downloaded

                    # asset_counts is optional here; keep existing value if present
                    row = self.repo.get_raw_ingest(context_id, columns='asset_counts') or {}
                    asset_counts = row.get('asset_counts') or {}
                    self.repo.update_raw_ingest_assets(context_id, merged_assets, asset_counts)
                except Exception as e:
                    logger.warning("Could not update raw_ingest assets metadata: %s", e)
                
                return storage_path
                
        except Exception as e:
            logger.error(f"Failed to download {url}: {str(e)}")
            return None
    
    def create_ocr_queue_entry(
        self,
        storage_path: str,
        context_id: str,
        asset_type: str,
        priority: str = 'medium'
    ) -> str:
        """
        Create queue entry for OCR processing
        
        Args:
            storage_path: Supabase Storage object path
            context_id: Associated context document ID
            asset_type: Asset type
            priority: Processing priority
            
        Returns:
            Queue entry document ID
        """
        queue_entry = {
            'storage_path': storage_path,
            'context_id': context_id,
            'asset_type': asset_type,
            'priority': priority,
            'status': 'pending',
            'created_at': utc_now_iso(),
            'attempts': 0,
            'max_attempts': 3
        }

        queue_id = self.repo.insert_ocr_queue(queue_entry)
        logger.info(f"Created OCR queue entry: {queue_id}")
        return queue_id
    
    def get_statistics(self) -> Dict[str, int]:
        """
        Get segregation statistics
        
        Returns:
            Dict with asset type counts
        """
        stats = {
            'total_documents': 0,
            'html_pages': 0,
            'pdf_files': 0,
            'images': 0,
            'ocr_pending': 0
        }
        
        # Best-effort statistics (requires raw_ingest table to exist)
        try:
            resp = self.repo.supabase.table('raw_ingest').select('asset_counts,processing_status').limit(1000).execute()
            rows = list(getattr(resp, 'data', None) or [])
            for row in rows:
                stats['total_documents'] += 1
                asset_counts = row.get('asset_counts') or {}
                stats['pdf_files'] += int(asset_counts.get('pdf') or 0)
                stats['images'] += int(asset_counts.get('images') or 0)
                ps = row.get('processing_status') or {}
                if ps.get('ocr_required') is True:
                    stats['ocr_pending'] += 1

            logger.info(f"Statistics: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Failed to get statistics: {str(e)}")
            return stats


# Example usage
def main():
    """Example usage"""
    segregator = AssetSegregator()
    
    # Example context object
    context_obj = {
        'url': 'http://www.epid.gov.lk/index.html',
        'content': {
            'links': {
                'internal': [
                    'http://www.epid.gov.lk/report.pdf',
                    'http://www.epid.gov.lk/circular.pdf',
                    'http://www.epid.gov.lk/image.jpg'
                ]
            },
            'media': {
                'images': ['http://www.epid.gov.lk/logo.png']
            }
        },
        'priority': 'high'
    }
    
    result = segregator.segregate_from_context(context_obj)
    print(f"Segregated: {result['asset_counts']}")


if __name__ == "__main__":
    main()
