"""
Asset Segregator
Separates HTML content from PDFs and images for appropriate processing
"""

import os
import mimetypes
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse
import logging
from pathlib import Path

from firebase_admin_setup import get_db, get_bucket  # type: ignore
from google.cloud.firestore import SERVER_TIMESTAMP  # type: ignore

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
    
    def __init__(self):
        """Initialize asset segregator"""
        self.db = get_db()
        self.bucket = get_bucket()
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
        Download asset and store in Firebase Storage
        
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
                
                # Upload to Firebase Storage
                blob = self.bucket.blob(storage_path)
                blob.upload_from_string(
                    response.content,
                    content_type=response.headers.get('content-type', 'application/octet-stream')
                )
                
                logger.info(f"✓ Uploaded to storage: {storage_path}")
                
                # Update Firestore with storage reference
                self.db.collection('raw_ingest').document(context_id).update({
                    f'assets.downloaded.{asset_type}': {
                        'url': url,
                        'storage_path': storage_path,
                        'uploaded_at': SERVER_TIMESTAMP,
                        'size_bytes': len(response.content)
                    }
                })
                
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
            storage_path: Firebase Storage path
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
            'created_at': SERVER_TIMESTAMP,
            'attempts': 0,
            'max_attempts': 3
        }
        
        doc_ref = self.db.collection('ocr_queue').document()
        doc_ref.set(queue_entry)
        
        logger.info(f"Created OCR queue entry: {doc_ref.id}")
        return doc_ref.id
    
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
        
        # Query Firestore for counts
        try:
            raw_ingest = self.db.collection('raw_ingest').stream()
            for doc in raw_ingest:
                data = doc.to_dict()
                stats['total_documents'] += 1
                
                asset_counts = data.get('asset_counts', {})
                stats['pdf_files'] += asset_counts.get('pdf', 0)
                stats['images'] += asset_counts.get('images', 0)
                
                if data.get('processing_status', {}).get('ocr_required', False):
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
