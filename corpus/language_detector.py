"""
Language Detection Module

Detects Sinhala, Tamil, English, and mixed-script content.
Uses Unicode range detection for native scripts and langdetect as fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class Language(str, Enum):
    """Supported languages."""
    SINHALA = "sinhala"
    TAMIL = "tamil"
    ENGLISH = "english"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ScriptType(str, Enum):
    """Script types."""
    SINHALA_SCRIPT = "sinhala_script"
    TAMIL_SCRIPT = "tamil_script"
    LATIN = "latin"
    MIXED = "mixed"
    NUMERIC = "numeric"
    UNKNOWN = "unknown"


@dataclass
class LanguageResult:
    """Result of language detection."""
    language: Language
    confidence: float
    script_type: ScriptType
    script_distribution: Dict[str, float]
    is_mixed_script: bool = False
    dominant_script: Optional[str] = None


class LanguageDetector:
    """
    Detects language from text supporting Sinhala, Tamil, English.
    
    Uses Unicode range detection for native scripts:
    - Sinhala: U+0D80 to U+0DFF
    - Tamil: U+0B80 to U+0BFF
    - Latin: Basic Latin and Latin Extended
    """
    
    # Unicode ranges for scripts
    SINHALA_RANGE = (0x0D80, 0x0DFF)
    TAMIL_RANGE = (0x0B80, 0x0BFF)
    LATIN_RANGE = (0x0041, 0x007A)  # Basic Latin letters
    LATIN_EXTENDED = (0x00C0, 0x024F)  # Latin Extended
    
    # Minimum characters to make a reliable detection
    MIN_CHARS_FOR_DETECTION = 3
    
    # Threshold for script dominance
    DOMINANCE_THRESHOLD = 0.7
    MIXED_THRESHOLD = 0.2
    
    def __init__(self, use_langdetect_fallback: bool = True):
        """
        Initialize the language detector.
        
        Args:
            use_langdetect_fallback: Use langdetect for Latin text classification
        """
        self.use_langdetect_fallback = use_langdetect_fallback
        self._langdetect_available = False
        
        if use_langdetect_fallback:
            try:
                from langdetect import detect, detect_langs
                self._langdetect_available = True
            except ImportError:
                logger.warning("langdetect not installed, using basic Latin detection")
    
    def _is_sinhala_char(self, char: str) -> bool:
        """Check if character is Sinhala script."""
        code = ord(char)
        return self.SINHALA_RANGE[0] <= code <= self.SINHALA_RANGE[1]
    
    def _is_tamil_char(self, char: str) -> bool:
        """Check if character is Tamil script."""
        code = ord(char)
        return self.TAMIL_RANGE[0] <= code <= self.TAMIL_RANGE[1]
    
    def _is_latin_char(self, char: str) -> bool:
        """Check if character is Latin script."""
        code = ord(char)
        return (
            (self.LATIN_RANGE[0] <= code <= self.LATIN_RANGE[1]) or
            (self.LATIN_EXTENDED[0] <= code <= self.LATIN_EXTENDED[1])
        )
    
    def detect_script(self, text: str) -> ScriptType:
        """
        Detect the primary script type in text.
        
        Args:
            text: Input text
            
        Returns:
            Primary script type
        """
        distribution = self.get_script_distribution(text)
        
        if not distribution:
            return ScriptType.UNKNOWN
        
        # Find dominant script
        max_script = max(distribution, key=distribution.get)
        max_ratio = distribution[max_script]
        
        if max_ratio >= self.DOMINANCE_THRESHOLD:
            if max_script == "sinhala":
                return ScriptType.SINHALA_SCRIPT
            elif max_script == "tamil":
                return ScriptType.TAMIL_SCRIPT
            elif max_script == "latin":
                return ScriptType.LATIN
        
        # Check for mixed script
        script_count = sum(1 for ratio in distribution.values() if ratio >= self.MIXED_THRESHOLD)
        if script_count >= 2:
            return ScriptType.MIXED
        
        return ScriptType.UNKNOWN
    
    def get_script_distribution(self, text: str) -> Dict[str, float]:
        """
        Get the distribution of scripts in text.
        
        Args:
            text: Input text
            
        Returns:
            Dict with script names and their ratios (0.0 to 1.0)
        """
        counts = {
            "sinhala": 0,
            "tamil": 0,
            "latin": 0,
            "other": 0
        }
        
        total_chars = 0
        
        for char in text:
            if char.isspace() or char in '.,!?;:()[]{}"\'-':
                continue
            
            total_chars += 1
            
            if self._is_sinhala_char(char):
                counts["sinhala"] += 1
            elif self._is_tamil_char(char):
                counts["tamil"] += 1
            elif self._is_latin_char(char):
                counts["latin"] += 1
            elif char.isdigit():
                continue  # Don't count digits
            else:
                counts["other"] += 1
        
        if total_chars == 0:
            return {}
        
        return {script: count / total_chars for script, count in counts.items()}
    
    def detect(self, text: str) -> LanguageResult:
        """
        Detect language from text.
        
        Args:
            text: Input text
            
        Returns:
            LanguageResult with language, confidence, and script info
        """
        if not text or len(text.strip()) < self.MIN_CHARS_FOR_DETECTION:
            return LanguageResult(
                language=Language.UNKNOWN,
                confidence=0.0,
                script_type=ScriptType.UNKNOWN,
                script_distribution={},
                is_mixed_script=False
            )
        
        # Get script distribution
        distribution = self.get_script_distribution(text)
        script_type = self.detect_script(text)
        
        # Detect language based on script
        if script_type == ScriptType.SINHALA_SCRIPT:
            return LanguageResult(
                language=Language.SINHALA,
                confidence=distribution.get("sinhala", 0.0),
                script_type=script_type,
                script_distribution=distribution,
                is_mixed_script=False,
                dominant_script="sinhala"
            )
        
        elif script_type == ScriptType.TAMIL_SCRIPT:
            return LanguageResult(
                language=Language.TAMIL,
                confidence=distribution.get("tamil", 0.0),
                script_type=script_type,
                script_distribution=distribution,
                is_mixed_script=False,
                dominant_script="tamil"
            )
        
        elif script_type == ScriptType.LATIN:
            # For Latin script, could be English, Singlish, or Tamilish
            # Use langdetect for English vs other Latin languages
            confidence = distribution.get("latin", 0.0)
            
            if self._langdetect_available:
                try:
                    from langdetect import detect_langs
                    langs = detect_langs(text)
                    if langs:
                        top_lang = langs[0]
                        if top_lang.lang == 'en':
                            return LanguageResult(
                                language=Language.ENGLISH,
                                confidence=top_lang.prob,
                                script_type=script_type,
                                script_distribution=distribution,
                                is_mixed_script=False,
                                dominant_script="latin"
                            )
                except Exception:
                    pass
            
            # Default to English for Latin script
            return LanguageResult(
                language=Language.ENGLISH,
                confidence=confidence,
                script_type=script_type,
                script_distribution=distribution,
                is_mixed_script=False,
                dominant_script="latin"
            )
        
        elif script_type == ScriptType.MIXED:
            # Determine dominant language in mixed script
            max_script = max(
                [(k, v) for k, v in distribution.items() if k != "other"],
                key=lambda x: x[1],
                default=("unknown", 0.0)
            )
            
            if max_script[0] == "sinhala":
                language = Language.SINHALA
            elif max_script[0] == "tamil":
                language = Language.TAMIL
            else:
                language = Language.MIXED
            
            return LanguageResult(
                language=language,
                confidence=max_script[1],
                script_type=script_type,
                script_distribution=distribution,
                is_mixed_script=True,
                dominant_script=max_script[0]
            )
        
        return LanguageResult(
            language=Language.UNKNOWN,
            confidence=0.0,
            script_type=script_type,
            script_distribution=distribution,
            is_mixed_script=False
        )
    
    def detect_batch(self, texts: List[str]) -> List[LanguageResult]:
        """
        Detect language for multiple texts.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of LanguageResult objects
        """
        return [self.detect(text) for text in texts]
    
    def is_native_script(self, text: str) -> bool:
        """
        Check if text contains native Sinhala or Tamil script.
        
        Args:
            text: Input text
            
        Returns:
            True if text contains native script
        """
        distribution = self.get_script_distribution(text)
        return (
            distribution.get("sinhala", 0) > 0.1 or
            distribution.get("tamil", 0) > 0.1
        )
    
    def contains_sinhala(self, text: str) -> bool:
        """Check if text contains Sinhala characters."""
        return any(self._is_sinhala_char(c) for c in text)
    
    def contains_tamil(self, text: str) -> bool:
        """Check if text contains Tamil characters."""
        return any(self._is_tamil_char(c) for c in text)
    
    def extract_by_script(self, text: str, script: ScriptType) -> str:
        """
        Extract only characters of a specific script.
        
        Args:
            text: Input text
            script: Target script type
            
        Returns:
            Filtered text containing only target script characters
        """
        result = []
        
        for char in text:
            if char.isspace():
                result.append(char)
                continue
            
            if script == ScriptType.SINHALA_SCRIPT and self._is_sinhala_char(char):
                result.append(char)
            elif script == ScriptType.TAMIL_SCRIPT and self._is_tamil_char(char):
                result.append(char)
            elif script == ScriptType.LATIN and self._is_latin_char(char):
                result.append(char)
        
        return ''.join(result).strip()


# Convenience function
def detect_language(text: str) -> LanguageResult:
    """Convenience function to detect language."""
    detector = LanguageDetector()
    return detector.detect(text)
