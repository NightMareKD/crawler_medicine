"""
Romanized Script Classifier

Classifies Latin-script text as:
- Pure English
- Singlish (Romanized Sinhala mixed with English)
- Tamilish (Romanized Tamil mixed with English)
- Mixed (Code-switching between languages)

Uses pattern matching with Singlish/Tamilish markers and n-gram analysis.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class RomanizedType(str, Enum):
    """Types of Romanized text."""
    PURE_ENGLISH = "pure_english"
    SINGLISH = "singlish"
    TAMILISH = "tamilish"
    MIXED = "mixed"  # Contains both Singlish and Tamilish markers
    UNKNOWN = "unknown"


@dataclass
class CodeSwitch:
    """Represents a code-switching point in text."""
    start_pos: int
    end_pos: int
    from_lang: str
    to_lang: str
    text_segment: str


@dataclass
class RomanizedResult:
    """Result of Romanized text classification."""
    classification: RomanizedType
    confidence: float
    singlish_score: float
    tamilish_score: float
    english_score: float
    matched_markers: List[str] = field(default_factory=list)
    code_switches: List[CodeSwitch] = field(default_factory=list)
    is_code_mixed: bool = False


class RomanizedClassifier:
    """
    Classifies Romanized text as English, Singlish, or Tamilish.
    
    Uses marker-based detection for Singlish/Tamilish patterns
    combined with statistical analysis.
    """
    
    # Default marker sets (can be overridden by loading patterns file)
    DEFAULT_SINGLISH_MARKERS = {
        "question_words": ["koheda", "mokakda", "kawda", "keeyada", "aida", "monawada"],
        "pronouns": ["mama", "oya", "api", "umba", "eyaa", "mage", "oyage"],
        "particles": ["da", "neda", "ne", "ko", "lu", "ado", "aney"],
        "verbs": ["ganna", "yanna", "enna", "kanna", "bonna", "karanna", "innava"],
        "common_phrases": ["kohomada", "mokada", "harida", "epane", "ithin", "namuth"]
    }
    
    DEFAULT_TAMILISH_MARKERS = {
        "question_words": ["enna", "enga", "eppo", "evlo", "yaru", "ethu"],
        "pronouns": ["naan", "nee", "avan", "aval", "naanga", "neengal"],
        "particles": ["la", "le", "lam", "pola", "thaan", "um"],
        "verbs": ["vaa", "poo", "saapdu", "paru", "keelu", "sollu", "pannunga"],
        "common_phrases": ["epdi", "inga", "anga", "appuram", "mudiyuma", "theriyuma", "illai"]
    }
    
    # English health domain terms (these don't count as Singlish/Tamilish indicators)
    ENGLISH_HEALTH_TERMS = {
        "clinic", "hospital", "doctor", "fever", "dengue", "vaccine", 
        "appointment", "opd", "patient", "medicine", "pharmacy", "emergency"
    }
    
    # Confidence thresholds
    SINGLISH_THRESHOLD = 0.3
    TAMILISH_THRESHOLD = 0.3
    ENGLISH_THRESHOLD = 0.7
    
    def __init__(self, patterns_file: Optional[Path] = None):
        """
        Initialize the classifier.
        
        Args:
            patterns_file: Optional path to JSON file with marker patterns
        """
        self.singlish_markers = self._flatten_markers(self.DEFAULT_SINGLISH_MARKERS)
        self.tamilish_markers = self._flatten_markers(self.DEFAULT_TAMILISH_MARKERS)
        
        # Load custom patterns if provided
        if patterns_file and patterns_file.exists():
            self._load_patterns(patterns_file)
        else:
            # Try to load default patterns file
            default_path = Path(__file__).parent / "training_data" / "romanized_patterns.json"
            if default_path.exists():
                self._load_patterns(default_path)
    
    def _flatten_markers(self, marker_dict: Dict[str, List[str]]) -> set:
        """Flatten marker dictionary to a set of all markers."""
        markers = set()
        for category_markers in marker_dict.values():
            markers.update(m.lower() for m in category_markers)
        return markers
    
    def _load_patterns(self, path: Path) -> None:
        """Load patterns from JSON file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if "singlish_markers" in data:
                self.singlish_markers = self._flatten_markers(data["singlish_markers"])
            if "tamilish_markers" in data:
                self.tamilish_markers = self._flatten_markers(data["tamilish_markers"])
            
            logger.info(f"Loaded patterns from {path}")
        except Exception as e:
            logger.warning(f"Failed to load patterns from {path}: {e}")
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        # Simple tokenization - split on whitespace and punctuation
        text = text.lower()
        tokens = re.findall(r'\b[a-z]+\b', text)
        return tokens
    
    def _count_marker_matches(
        self, 
        tokens: List[str], 
        markers: set
    ) -> Tuple[int, List[str]]:
        """
        Count how many tokens match markers.
        
        Returns:
            Tuple of (count, matched_markers)
        """
        matched = []
        for token in tokens:
            if token in markers:
                matched.append(token)
        return len(matched), matched
    
    def _calculate_scores(
        self, 
        tokens: List[str]
    ) -> Tuple[float, float, float, List[str]]:
        """
        Calculate language scores for tokens.
        
        Returns:
            Tuple of (singlish_score, tamilish_score, english_score, all_matched)
        """
        if not tokens:
            return 0.0, 0.0, 0.0, []
        
        # Filter out common English health terms for marker matching
        filtered_tokens = [t for t in tokens if t not in self.ENGLISH_HEALTH_TERMS]
        
        if not filtered_tokens:
            # All tokens are common English terms
            return 0.0, 0.0, 1.0, []
        
        # Count matches
        singlish_count, singlish_matched = self._count_marker_matches(
            filtered_tokens, self.singlish_markers
        )
        tamilish_count, tamilish_matched = self._count_marker_matches(
            filtered_tokens, self.tamilish_markers
        )
        
        # Calculate scores based on proportion of matched markers
        total_non_english = len(filtered_tokens)
        
        singlish_score = singlish_count / total_non_english if total_non_english > 0 else 0
        tamilish_score = tamilish_count / total_non_english if total_non_english > 0 else 0
        
        # English score is inverse of marker matches
        english_score = 1.0 - max(singlish_score, tamilish_score)
        
        all_matched = singlish_matched + tamilish_matched
        
        return singlish_score, tamilish_score, english_score, all_matched
    
    def classify(self, text: str) -> RomanizedResult:
        """
        Classify Romanized text.
        
        Args:
            text: Input text (should be Latin script)
            
        Returns:
            RomanizedResult with classification and scores
        """
        if not text or not text.strip():
            return RomanizedResult(
                classification=RomanizedType.UNKNOWN,
                confidence=0.0,
                singlish_score=0.0,
                tamilish_score=0.0,
                english_score=0.0
            )
        
        tokens = self._tokenize(text)
        
        if not tokens:
            return RomanizedResult(
                classification=RomanizedType.UNKNOWN,
                confidence=0.0,
                singlish_score=0.0,
                tamilish_score=0.0,
                english_score=0.0
            )
        
        singlish_score, tamilish_score, english_score, matched = self._calculate_scores(tokens)
        
        # Determine classification
        if singlish_score >= self.SINGLISH_THRESHOLD and tamilish_score >= self.TAMILISH_THRESHOLD:
            classification = RomanizedType.MIXED
            confidence = max(singlish_score, tamilish_score)
        elif singlish_score >= self.SINGLISH_THRESHOLD:
            classification = RomanizedType.SINGLISH
            confidence = min(1.0, singlish_score + 0.3)  # Boost confidence
        elif tamilish_score >= self.TAMILISH_THRESHOLD:
            classification = RomanizedType.TAMILISH
            confidence = min(1.0, tamilish_score + 0.3)
        elif english_score >= self.ENGLISH_THRESHOLD:
            classification = RomanizedType.PURE_ENGLISH
            confidence = english_score
        else:
            # Low scores all around - likely English with some ambiguous words
            classification = RomanizedType.PURE_ENGLISH
            confidence = 0.6
        
        # Detect code switches
        code_switches = self.extract_code_switches(text)
        is_code_mixed = len(code_switches) > 0
        
        return RomanizedResult(
            classification=classification,
            confidence=confidence,
            singlish_score=singlish_score,
            tamilish_score=tamilish_score,
            english_score=english_score,
            matched_markers=matched,
            code_switches=code_switches,
            is_code_mixed=is_code_mixed
        )
    
    def extract_code_switches(self, text: str) -> List[CodeSwitch]:
        """
        Identify code-switching points in text.
        
        Args:
            text: Input text
            
        Returns:
            List of CodeSwitch objects
        """
        switches = []
        tokens = self._tokenize(text)
        
        if len(tokens) < 2:
            return switches
        
        prev_lang = self._get_token_language(tokens[0])
        switch_start = 0
        
        for i, token in enumerate(tokens[1:], 1):
            curr_lang = self._get_token_language(token)
            
            if curr_lang != prev_lang and curr_lang != "unknown" and prev_lang != "unknown":
                # Find position in original text (approximate)
                token_pos = text.lower().find(token)
                
                switches.append(CodeSwitch(
                    start_pos=token_pos,
                    end_pos=token_pos + len(token),
                    from_lang=prev_lang,
                    to_lang=curr_lang,
                    text_segment=token
                ))
            
            if curr_lang != "unknown":
                prev_lang = curr_lang
        
        return switches
    
    def _get_token_language(self, token: str) -> str:
        """Determine language of a single token."""
        token = token.lower()
        
        if token in self.singlish_markers:
            return "singlish"
        elif token in self.tamilish_markers:
            return "tamilish"
        elif token in self.ENGLISH_HEALTH_TERMS:
            return "english"
        else:
            return "unknown"
    
    def classify_batch(self, texts: List[str]) -> List[RomanizedResult]:
        """
        Classify multiple texts.
        
        Args:
            texts: List of input texts
            
        Returns:
            List of RomanizedResult objects
        """
        return [self.classify(text) for text in texts]
    
    def is_romanized_local(self, text: str) -> bool:
        """
        Check if text contains Romanized local language (Singlish or Tamilish).
        
        Args:
            text: Input text
            
        Returns:
            True if text contains Singlish or Tamilish markers
        """
        result = self.classify(text)
        return result.classification in (
            RomanizedType.SINGLISH, 
            RomanizedType.TAMILISH, 
            RomanizedType.MIXED
        )
    
    def get_language_for_translation(self, text: str) -> Optional[str]:
        """
        Determine the target language for transliteration/translation.
        
        Args:
            text: Input text
            
        Returns:
            'sinhala', 'tamil', or None if pure English
        """
        result = self.classify(text)
        
        if result.classification == RomanizedType.SINGLISH:
            return "sinhala"
        elif result.classification == RomanizedType.TAMILISH:
            return "tamil"
        elif result.classification == RomanizedType.MIXED:
            # Return dominant language
            if result.singlish_score > result.tamilish_score:
                return "sinhala"
            else:
                return "tamil"
        
        return None


# Convenience function
def classify_romanized(text: str) -> RomanizedResult:
    """Convenience function to classify Romanized text."""
    classifier = RomanizedClassifier()
    return classifier.classify(text)
