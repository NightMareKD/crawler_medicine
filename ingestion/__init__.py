"""
Data Ingestion Layer
Layer 1: Polite web crawling, asset segregation, and OCR processing
"""

# Keep package import lightweight. Individual modules may depend on optional
# runtime packages (e.g., Crawl4AI) and should be imported directly.
__all__ = [
	'AdaptiveCrawlerAgent',
	'AssetSegregator',
	'URLManager',
	'OCRProcessor',
]


def __getattr__(name: str):
	if name == 'AdaptiveCrawlerAgent':
		from .crawler_agent import AdaptiveCrawlerAgent

		return AdaptiveCrawlerAgent
	if name == 'AssetSegregator':
		from .asset_segregator import AssetSegregator

		return AssetSegregator
	if name == 'URLManager':
		from .url_manager import URLManager

		return URLManager
	if name == 'OCRProcessor':
		from .ocr_processor import OCRProcessor

		return OCRProcessor
	raise AttributeError(name)
