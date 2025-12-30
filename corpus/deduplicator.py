"""
Content Deduplication & Versioning

Detects duplicate and near-duplicate content:
- SimHash for similarity detection
- Content versioning for updates
- Change tracking
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class DuplicateMatch:
    """A duplicate content match."""
    original_id: str
    original_url: str
    similarity_score: float
    is_exact: bool


@dataclass
class VersionInfo:
    """Content version information."""
    version_number: int
    content_hash: str
    previous_version_id: Optional[str] = None
    changes_summary: Optional[str] = None


class ContentDeduplicator:
    """
    Detects and handles duplicate content.
    
    Uses content hashing for exact duplicates and
    simplified similarity for near-duplicates.
    """
    
    def __init__(self, repo: Optional[Any] = None):
        """
        Initialize the deduplicator.
        
        Args:
            repo: SupabaseRepo instance
        """
        self.repo = repo
    
    def compute_hash(self, text: str) -> str:
        """
        Compute content hash for deduplication.
        
        Args:
            text: Input text
            
        Returns:
            SHA-256 hash of normalized text
        """
        # Normalize text for consistent hashing
        normalized = self._normalize_for_hash(text)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    
    def _normalize_for_hash(self, text: str) -> str:
        """Normalize text for consistent hashing."""
        # Lowercase
        text = text.lower()
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        return text.strip()
    
    def is_duplicate(
        self,
        text: str,
        repo: Optional[Any] = None
    ) -> Tuple[bool, Optional[DuplicateMatch]]:
        """
        Check if content already exists.
        
        Args:
            text: Content to check
            repo: Optional repo override
            
        Returns:
            Tuple of (is_duplicate, match_info)
        """
        repo = repo or self.repo
        if not repo:
            return False, None
        
        content_hash = self.compute_hash(text)
        
        # Check for exact match
        existing = repo.find_by_content_hash(content_hash)
        
        if existing:
            return True, DuplicateMatch(
                original_id=existing["id"],
                original_url=existing.get("url", ""),
                similarity_score=1.0,
                is_exact=True
            )
        
        return False, None
    
    def find_near_duplicates(
        self,
        text: str,
        threshold: float = 0.9,
        repo: Optional[Any] = None,
        limit: int = 100
    ) -> List[DuplicateMatch]:
        """
        Find near-duplicate documents.
        
        This is a simplified implementation using token overlap.
        For production, consider using SimHash or MinHash.
        
        Args:
            text: Text to compare
            threshold: Similarity threshold (0.0 to 1.0)
            repo: Optional repo override
            limit: Max documents to compare
            
        Returns:
            List of similar documents
        """
        repo = repo or self.repo
        if not repo:
            return []
        
        # Get target tokens
        target_tokens = set(self._normalize_for_hash(text).split())
        
        if len(target_tokens) < 5:
            return []  # Too short for meaningful comparison
        
        matches = []
        
        try:
            # Fetch recent documents for comparison
            resp = repo.supabase.table("raw_ingest").select(
                "id,url,content"
            ).limit(limit).execute()
            
            rows = getattr(resp, "data", None) or []
            
            for row in rows:
                content = row.get("content", {})
                if isinstance(content, dict):
                    doc_text = content.get("markdown", "") or content.get("cleaned_html", "")
                else:
                    doc_text = str(content) if content else ""
                
                if not doc_text:
                    continue
                
                # Calculate Jaccard similarity
                doc_tokens = set(self._normalize_for_hash(doc_text).split())
                
                if not doc_tokens:
                    continue
                
                intersection = len(target_tokens & doc_tokens)
                union = len(target_tokens | doc_tokens)
                
                if union == 0:
                    continue
                
                similarity = intersection / union
                
                if similarity >= threshold:
                    matches.append(DuplicateMatch(
                        original_id=row["id"],
                        original_url=row.get("url", ""),
                        similarity_score=similarity,
                        is_exact=(similarity == 1.0)
                    ))
        
        except Exception as e:
            logger.error(f"Error finding near duplicates: {e}")
        
        # Sort by similarity
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        return matches
    
    def create_version(
        self,
        context_id: str,
        new_content: str,
        repo: Optional[Any] = None
    ) -> Optional[VersionInfo]:
        """
        Create a new version if content has changed.
        
        Args:
            context_id: Document context ID
            new_content: New content
            repo: Optional repo override
            
        Returns:
            VersionInfo if new version created, None if no change
        """
        repo = repo or self.repo
        if not repo:
            return None
        
        new_hash = self.compute_hash(new_content)
        
        try:
            # Get existing versions
            versions = repo.get_content_versions(context_id)
            
            if not versions:
                # First version
                version_id = repo.insert_content_version(
                    context_id=context_id,
                    content_hash=new_hash,
                    version_number=1
                )
                
                # Update document hash
                repo.update_content_hash(context_id, new_hash)
                
                return VersionInfo(
                    version_number=1,
                    content_hash=new_hash
                )
            
            # Check if content changed
            latest = versions[0]
            if latest.get("content_hash") == new_hash:
                return None  # No change
            
            # Create new version
            new_version = latest.get("version_number", 0) + 1
            
            version_id = repo.insert_content_version(
                context_id=context_id,
                content_hash=new_hash,
                version_number=new_version,
                previous_version_id=latest.get("id"),
                changes_summary=f"Updated from version {new_version - 1}"
            )
            
            # Update document hash
            repo.update_content_hash(context_id, new_hash)
            
            logger.info(f"Created version {new_version} for {context_id}")
            
            return VersionInfo(
                version_number=new_version,
                content_hash=new_hash,
                previous_version_id=latest.get("id")
            )
        
        except Exception as e:
            logger.error(f"Error creating version: {e}")
            return None
    
    def get_version_history(
        self,
        context_id: str,
        repo: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Get version history for a document.
        
        Args:
            context_id: Document context ID
            repo: Optional repo override
            
        Returns:
            List of version records
        """
        repo = repo or self.repo
        if not repo:
            return []
        
        return repo.get_content_versions(context_id)
    
    def compute_diff_summary(
        self,
        old_text: str,
        new_text: str
    ) -> str:
        """
        Compute a summary of changes between two texts.
        
        Args:
            old_text: Original text
            new_text: New text
            
        Returns:
            Summary of changes
        """
        old_words = len(old_text.split())
        new_words = len(new_text.split())
        
        word_diff = new_words - old_words
        
        if word_diff > 0:
            return f"Added ~{word_diff} words"
        elif word_diff < 0:
            return f"Removed ~{abs(word_diff)} words"
        else:
            return "Minor changes (same word count)"


# Convenience functions
def check_duplicate(text: str, repo: Any) -> Tuple[bool, Optional[DuplicateMatch]]:
    """Convenience function to check for duplicates."""
    dedup = ContentDeduplicator(repo)
    return dedup.is_duplicate(text)


def compute_content_hash(text: str) -> str:
    """Convenience function to compute content hash."""
    dedup = ContentDeduplicator()
    return dedup.compute_hash(text)
