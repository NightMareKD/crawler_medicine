"""
Text Preprocessing Pipeline

Provides text cleaning, normalization, sentence segmentation,
and PII (Personally Identifiable Information) detection/removal
for multilingual health corpus data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class PIIType(str, Enum):
    """Types of PII that can be detected."""
    PHONE = "phone"
    EMAIL = "email"
    NIC = "nic"  # National Identity Card (Sri Lanka)
    PASSPORT = "passport"
    ADDRESS = "address"
    NAME = "name"


@dataclass
class PIIMatch:
    """A detected PII match."""
    pii_type: PIIType
    start: int
    end: int
    original_text: str
    masked_text: str = "[REDACTED]"


@dataclass
class PreprocessingResult:
    """Result of text preprocessing."""
    original_text: str
    cleaned_text: str
    pii_detected: List[PIIMatch] = field(default_factory=list)
    pii_removed: bool = False
    sentences: List[str] = field(default_factory=list)


class TextPreprocessor:
    """
    Cleans and normalizes multilingual text for health corpus.
    
    Features:
    - Unicode normalization
    - Whitespace standardization
    - PII detection and masking
    - Sentence segmentation (language-aware)
    - Romanized text normalization
    """
    
    # Sri Lankan phone patterns
    PHONE_PATTERNS = [
        r'\b0\d{9}\b',                    # Local: 0771234567
        r'\b\+94\s?\d{9}\b',              # International: +94 771234567
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # Various formats
        r'\b\d{10}\b',                    # 10 digits
    ]
    
    # Email pattern
    EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    # Sri Lankan NIC patterns
    NIC_PATTERNS = [
        r'\b\d{9}[VvXx]\b',               # Old format: 123456789V
        r'\b\d{12}\b',                    # New format: 200012345678
    ]
    
    # Sinhala sentence endings
    SINHALA_SENTENCE_END = r'[.!?។]'
    
    # Tamil sentence endings
    TAMIL_SENTENCE_END = r'[.!?।]'
    
    # Common Romanized spelling variations to normalize
    ROMANIZED_NORMALIZATIONS = {
        # Singlish variations
        "kohenda": "koheda",
        "mokakda": "mokakda",
        "neda": "neda",
        "innawada": "innawada",
        # Common misspellings
        "hosiptal": "hospital",
        "docter": "doctor",
        "clinik": "clinic",
        "vacine": "vaccine",
    }
    
    def __init__(
        self,
        remove_pii: bool = True,
        normalize_romanized: bool = True,
        mask_string: str = "[REDACTED]"
    ):
        """
        Initialize preprocessor.
        
        Args:
            remove_pii: Whether to remove detected PII
            normalize_romanized: Whether to normalize Romanized spellings
            mask_string: String to replace PII with
        """
        self.remove_pii = remove_pii
        self.normalize_romanized = normalize_romanized
        self.mask_string = mask_string
        
        # Compile patterns
        self._phone_patterns = [re.compile(p) for p in self.PHONE_PATTERNS]
        self._email_pattern = re.compile(self.EMAIL_PATTERN)
        self._nic_patterns = [re.compile(p) for p in self.NIC_PATTERNS]
    
    def clean(self, text: str) -> str:
        """
        Clean text by removing noise and normalizing.
        
        Args:
            text: Input text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Normalize Unicode
        import unicodedata
        text = unicodedata.normalize('NFC', text)
        
        # Remove control characters (except newlines)
        text = ''.join(c for c in text if c == '\n' or not unicodedata.category(c).startswith('C'))
        
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove leading/trailing whitespace from lines
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        return text.strip()
    
    def normalize_romanized_text(self, text: str) -> str:
        """
        Standardize Romanized spellings.
        
        Args:
            text: Input text
            
        Returns:
            Normalized text
        """
        if not self.normalize_romanized:
            return text
        
        result = text.lower()
        
        for variation, standard in self.ROMANIZED_NORMALIZATIONS.items():
            result = re.sub(
                r'\b' + re.escape(variation) + r'\b',
                standard,
                result,
                flags=re.IGNORECASE
            )
        
        return result
    
    def detect_pii(self, text: str) -> List[PIIMatch]:
        """
        Detect PII in text.
        
        Args:
            text: Input text
            
        Returns:
            List of PIIMatch objects
        """
        matches = []
        
        # Detect phone numbers
        for pattern in self._phone_patterns:
            for match in pattern.finditer(text):
                matches.append(PIIMatch(
                    pii_type=PIIType.PHONE,
                    start=match.start(),
                    end=match.end(),
                    original_text=match.group(),
                    masked_text=self.mask_string
                ))
        
        # Detect emails
        for match in self._email_pattern.finditer(text):
            matches.append(PIIMatch(
                pii_type=PIIType.EMAIL,
                start=match.start(),
                end=match.end(),
                original_text=match.group(),
                masked_text=self.mask_string
            ))
        
        # Detect NICs
        for pattern in self._nic_patterns:
            for match in pattern.finditer(text):
                matches.append(PIIMatch(
                    pii_type=PIIType.NIC,
                    start=match.start(),
                    end=match.end(),
                    original_text=match.group(),
                    masked_text=self.mask_string
                ))
        
        # Sort by position
        matches.sort(key=lambda m: m.start)
        
        return matches
    
    def mask_pii(self, text: str, pii_matches: List[PIIMatch]) -> str:
        """
        Mask detected PII in text.
        
        Args:
            text: Original text
            pii_matches: List of PIIMatch objects
            
        Returns:
            Text with PII masked
        """
        if not pii_matches:
            return text
        
        # Replace from end to start to preserve positions
        result = text
        for match in reversed(pii_matches):
            result = result[:match.start] + match.masked_text + result[match.end:]
        
        return result
    
    def segment_sentences(self, text: str, language: str = "english") -> List[str]:
        """
        Split text into sentences.
        
        Args:
            text: Input text
            language: Language for sentence splitting rules
            
        Returns:
            List of sentences
        """
        if not text:
            return []
        
        # Define sentence ending pattern based on language
        if language.lower() in ("sinhala", "si", "sin"):
            pattern = self.SINHALA_SENTENCE_END
        elif language.lower() in ("tamil", "ta", "tam"):
            pattern = self.TAMIL_SENTENCE_END
        else:
            pattern = r'[.!?]'
        
        # Split on sentence endings, keeping the delimiter
        sentences = re.split(f'({pattern})', text)
        
        # Recombine sentences with their endings
        result = []
        current = ""
        
        for part in sentences:
            if re.match(pattern, part):
                current += part
                if current.strip():
                    result.append(current.strip())
                current = ""
            else:
                current += part
        
        if current.strip():
            result.append(current.strip())
        
        return result
    
    def preprocess(
        self,
        text: str,
        language: str = "english",
        detect_pii_flag: bool = True
    ) -> PreprocessingResult:
        """
        Full preprocessing pipeline.
        
        Args:
            text: Input text
            language: Text language for sentence segmentation
            detect_pii_flag: Whether to detect and optionally remove PII
            
        Returns:
            PreprocessingResult with cleaned text and metadata
        """
        # Clean text
        cleaned = self.clean(text)
        
        # Normalize Romanized text if enabled
        if self.normalize_romanized:
            cleaned = self.normalize_romanized_text(cleaned)
        
        # Detect PII
        pii_matches = []
        pii_removed = False
        
        if detect_pii_flag:
            pii_matches = self.detect_pii(cleaned)
            
            if self.remove_pii and pii_matches:
                cleaned = self.mask_pii(cleaned, pii_matches)
                pii_removed = True
        
        # Segment sentences
        sentences = self.segment_sentences(cleaned, language)
        
        return PreprocessingResult(
            original_text=text,
            cleaned_text=cleaned,
            pii_detected=pii_matches,
            pii_removed=pii_removed,
            sentences=sentences
        )
    
    def preprocess_batch(
        self,
        texts: List[str],
        language: str = "english"
    ) -> List[PreprocessingResult]:
        """
        Preprocess multiple texts.
        
        Args:
            texts: List of texts
            language: Text language
            
        Returns:
            List of PreprocessingResult objects
        """
        return [self.preprocess(text, language) for text in texts]
    
    def extract_health_numbers(self, text: str) -> Dict[str, List[str]]:
        """
        Extract health-related numbers (not PII).
        
        Args:
            text: Input text
            
        Returns:
            Dict with categories of numbers found
        """
        numbers = {
            "temperatures": [],
            "phone_numbers": [],
            "times": [],
            "dates": []
        }
        
        # Temperature pattern (e.g., 98.6°F, 37°C)
        temp_pattern = r'\d{2,3}(?:\.\d)?°?[°CF]?'
        for match in re.finditer(temp_pattern, text):
            numbers["temperatures"].append(match.group())
        
        # Time pattern (e.g., 8am, 8:00 AM, 20:00)
        time_pattern = r'\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?'
        for match in re.finditer(time_pattern, text):
            numbers["times"].append(match.group())
        
        return numbers


# Convenience function
def preprocess_text(
    text: str,
    language: str = "english",
    remove_pii: bool = True
) -> PreprocessingResult:
    """Convenience function for text preprocessing."""
    preprocessor = TextPreprocessor(remove_pii=remove_pii)
    return preprocessor.preprocess(text, language)
