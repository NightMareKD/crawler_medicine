"""
Data Ingestion Layer
Layer 1: Polite web crawling, asset segregation, and OCR processing
"""

from .crawler_agent import AdaptiveCrawlerAgent
from .asset_segregator import AssetSegregator
from .url_manager import URLManager

__all__ = ['AdaptiveCrawlerAgent', 'AssetSegregator', 'URLManager']
