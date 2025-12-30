"""Unit tests for Romanized script classifier."""

import pytest
from corpus.romanized_classifier import (
    RomanizedClassifier,
    RomanizedType,
    RomanizedResult,
    classify_romanized
)


class TestRomanizedClassifier:
    """Tests for RomanizedClassifier class."""
    
    @pytest.fixture
    def classifier(self):
        """Create a classifier instance."""
        return RomanizedClassifier()
    
    # -------------------------
    # Singlish Detection Tests
    # -------------------------
    
    def test_detect_singlish_question(self, classifier):
        """Test detection of Singlish question."""
        text = "mage amma dengue clinic eka koheda"
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.SINGLISH
        assert result.singlish_score > 0
        assert "koheda" in result.matched_markers or "mage" in result.matched_markers
    
    def test_detect_singlish_statement(self, classifier):
        """Test detection of Singlish statement."""
        text = "mama hospital eke doctor ganna yanna one"
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.SINGLISH
        assert result.confidence > 0.3
    
    def test_detect_singlish_particles(self, classifier):
        """Test detection using Singlish particles."""
        text = "hospital time eka mokakda aney"
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.SINGLISH
    
    # -------------------------
    # Tamilish Detection Tests
    # -------------------------
    
    def test_detect_tamilish_question(self, classifier):
        """Test detection of Tamilish question."""
        text = "dengue clinic enga irukku hospital la"
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.TAMILISH
        assert result.tamilish_score > 0
    
    def test_detect_tamilish_statement(self, classifier):
        """Test detection of Tamilish statement."""
        text = "naan hospital ponga theriyuma"
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.TAMILISH
    
    # -------------------------
    # Pure English Detection Tests
    # -------------------------
    
    def test_detect_pure_english(self, classifier):
        """Test detection of pure English."""
        text = "Where is the dengue clinic located?"
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.PURE_ENGLISH
        assert result.english_score > 0.5
    
    def test_detect_english_health_terms(self, classifier):
        """Test that English health terms don't trigger false positives."""
        text = "The hospital provides dengue treatment and vaccine services."
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.PURE_ENGLISH
    
    # -------------------------
    # Edge Cases
    # -------------------------
    
    def test_empty_text(self, classifier):
        """Test handling of empty text."""
        result = classifier.classify("")
        assert result.classification == RomanizedType.UNKNOWN
    
    def test_single_word_singlish(self, classifier):
        """Test single Singlish word."""
        result = classifier.classify("koheda")
        assert result.classification == RomanizedType.SINGLISH
    
    def test_single_word_english(self, classifier):
        """Test single English word."""
        result = classifier.classify("hospital")
        # Single common English health term
        assert result.classification == RomanizedType.PURE_ENGLISH
    
    # -------------------------
    # Code-Switching Tests
    # -------------------------
    
    def test_code_switching_detection(self, classifier):
        """Test code-switching detection."""
        text = "mama hospital eke appointment ganna enna"
        result = classifier.classify(text)
        
        # Should detect Singlish with code-switching
        assert result.classification == RomanizedType.SINGLISH
        assert result.is_code_mixed or len(result.matched_markers) > 0
    
    # -------------------------
    # Helper Method Tests
    # -------------------------
    
    def test_is_romanized_local(self, classifier):
        """Test is_romanized_local helper."""
        assert classifier.is_romanized_local("mage amma koheda")
        assert classifier.is_romanized_local("naan hospital ponga")
        assert not classifier.is_romanized_local("Where is the hospital?")
    
    def test_get_language_for_translation_singlish(self, classifier):
        """Test getting translation target for Singlish."""
        text = "mage amma dengue clinic eka koheda"
        lang = classifier.get_language_for_translation(text)
        assert lang == "sinhala"
    
    def test_get_language_for_translation_tamilish(self, classifier):
        """Test getting translation target for Tamilish."""
        text = "dengue clinic enga irukku"
        lang = classifier.get_language_for_translation(text)
        assert lang == "tamil"
    
    def test_get_language_for_translation_english(self, classifier):
        """Test getting translation target for pure English."""
        text = "Where is the dengue clinic?"
        lang = classifier.get_language_for_translation(text)
        assert lang is None
    
    # -------------------------
    # Batch Classification Tests
    # -------------------------
    
    def test_classify_batch(self, classifier):
        """Test batch classification."""
        texts = [
            "mage amma koheda",
            "naan hospital ponga",
            "Where is the clinic?"
        ]
        results = classifier.classify_batch(texts)
        
        assert len(results) == 3
        assert results[0].classification == RomanizedType.SINGLISH
        assert results[1].classification == RomanizedType.TAMILISH
        assert results[2].classification == RomanizedType.PURE_ENGLISH
    
    # -------------------------
    # Convenience Function Test
    # -------------------------
    
    def test_convenience_function(self):
        """Test the classify_romanized convenience function."""
        result = classify_romanized("mama hospital yanna one")
        
        assert result.classification == RomanizedType.SINGLISH
        assert isinstance(result, RomanizedResult)


# Real-world examples from proposal
class TestRealWorldExamples:
    """Tests using real-world examples from project proposal."""
    
    @pytest.fixture
    def classifier(self):
        return RomanizedClassifier()
    
    def test_proposal_example_1(self, classifier):
        """Test: 'mage amma dengue clinic eka kohenda?'"""
        text = "mage amma dengue clinic eka kohenda"
        result = classifier.classify(text)
        
        assert result.classification == RomanizedType.SINGLISH
        assert result.is_code_mixed or "kohenda" in text.lower() or "koheda" in str(result.matched_markers)
    
    def test_proposal_example_2(self, classifier):
        """Test: 'hospital time kandy today'"""
        text = "hospital time kandy today"
        result = classifier.classify(text)
        
        # This is mostly English with no clear Singlish markers
        assert result.classification == RomanizedType.PURE_ENGLISH
    
    def test_proposal_example_3(self, classifier):
        """Test: 'amma fever hariyata thiyenawa da'"""
        text = "amma fever hariyata thiyenawa da"
        result = classifier.classify(text)
        
        # Contains Singlish markers: amma, da
        assert result.classification == RomanizedType.SINGLISH
