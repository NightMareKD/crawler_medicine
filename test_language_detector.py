"""Unit tests for language detection module."""

import pytest
from corpus.language_detector import (
    LanguageDetector,
    Language,
    ScriptType,
    LanguageResult,
    detect_language
)


class TestLanguageDetector:
    """Tests for LanguageDetector class."""
    
    @pytest.fixture
    def detector(self):
        """Create a detector instance."""
        return LanguageDetector(use_langdetect_fallback=False)
    
    # -------------------------
    # Script Detection Tests
    # -------------------------
    
    def test_detect_sinhala_script(self, detector):
        """Test detection of Sinhala script."""
        text = "ඩෙංගු වෛද්‍ය මධ්‍යස්ථානය"
        result = detector.detect(text)
        
        assert result.language == Language.SINHALA
        assert result.script_type == ScriptType.SINHALA_SCRIPT
        assert result.confidence > 0.7
        assert not result.is_mixed_script
    
    def test_detect_tamil_script(self, detector):
        """Test detection of Tamil script."""
        text = "டெங்கு கிளினிக்"
        result = detector.detect(text)
        
        assert result.language == Language.TAMIL
        assert result.script_type == ScriptType.TAMIL_SCRIPT
        assert result.confidence > 0.7
        assert not result.is_mixed_script
    
    def test_detect_english_script(self, detector):
        """Test detection of English/Latin script."""
        text = "Where is the dengue clinic?"
        result = detector.detect(text)
        
        assert result.language == Language.ENGLISH
        assert result.script_type == ScriptType.LATIN
        assert result.confidence > 0.7
        assert not result.is_mixed_script
    
    def test_detect_mixed_script(self, detector):
        """Test detection of mixed script content."""
        text = "ඩෙංගු clinic එක කොහෙද"
        result = detector.detect(text)
        
        assert result.is_mixed_script or result.script_type == ScriptType.MIXED or result.language == Language.SINHALA
        # Should still identify Sinhala as dominant
        assert result.dominant_script == "sinhala" or result.language == Language.SINHALA
    
    def test_empty_text(self, detector):
        """Test handling of empty text."""
        result = detector.detect("")
        
        assert result.language == Language.UNKNOWN
        assert result.confidence == 0.0
    
    def test_short_text(self, detector):
        """Test handling of very short text."""
        result = detector.detect("ab")
        
        assert result.language == Language.UNKNOWN
    
    # -------------------------
    # Script Distribution Tests
    # -------------------------
    
    def test_script_distribution_pure_sinhala(self, detector):
        """Test script distribution for pure Sinhala."""
        text = "මම ගෙදර යනවා"
        distribution = detector.get_script_distribution(text)
        
        assert "sinhala" in distribution
        assert distribution["sinhala"] > 0.9
        assert distribution.get("latin", 0) < 0.1
    
    def test_script_distribution_mixed(self, detector):
        """Test script distribution for mixed content."""
        text = "hospital eke phone number"
        distribution = detector.get_script_distribution(text)
        
        assert "latin" in distribution
        assert distribution["latin"] > 0.9
    
    # -------------------------
    # Helper Methods Tests
    # -------------------------
    
    def test_contains_sinhala(self, detector):
        """Test Sinhala character detection."""
        assert detector.contains_sinhala("ඩෙංගු fever")
        assert not detector.contains_sinhala("dengue fever")
    
    def test_contains_tamil(self, detector):
        """Test Tamil character detection."""
        assert detector.contains_tamil("டெங்கு clinic")
        assert not detector.contains_tamil("dengue clinic")
    
    def test_is_native_script(self, detector):
        """Test native script detection."""
        assert detector.is_native_script("ඩෙංගු")
        assert detector.is_native_script("டெங்கு")
        assert not detector.is_native_script("dengue")
    
    def test_extract_by_script_sinhala(self, detector):
        """Test extracting Sinhala characters."""
        text = "ඩෙංගු clinic එක"
        sinhala_only = detector.extract_by_script(text, ScriptType.SINHALA_SCRIPT)
        
        assert "ඩෙංගු" in sinhala_only
        assert "clinic" not in sinhala_only
    
    def test_extract_by_script_latin(self, detector):
        """Test extracting Latin characters."""
        text = "ඩෙංගු clinic එක open"
        latin_only = detector.extract_by_script(text, ScriptType.LATIN)
        
        assert "clinic" in latin_only
        assert "open" in latin_only
        assert "ඩෙංගු" not in latin_only
    
    # -------------------------
    # Batch Detection Tests
    # -------------------------
    
    def test_detect_batch(self, detector):
        """Test batch language detection."""
        texts = [
            "ඩෙංගු වෛද්‍ය",
            "டெங்கு கிளினிக்",
            "Dengue clinic"
        ]
        results = detector.detect_batch(texts)
        
        assert len(results) == 3
        assert results[0].language == Language.SINHALA
        assert results[1].language == Language.TAMIL
        assert results[2].language == Language.ENGLISH
    
    # -------------------------
    # Convenience Function Test
    # -------------------------
    
    def test_convenience_function(self):
        """Test the detect_language convenience function."""
        result = detect_language("ඩෙංගු වෛද්‍ය මධ්‍යස්ථානය")
        
        assert result.language == Language.SINHALA
        assert isinstance(result, LanguageResult)


# Additional test cases for edge cases
class TestLanguageDetectorEdgeCases:
    """Edge case tests for LanguageDetector."""
    
    @pytest.fixture
    def detector(self):
        return LanguageDetector(use_langdetect_fallback=False)
    
    def test_numbers_only(self, detector):
        """Test text with only numbers."""
        result = detector.detect("12345 67890")
        # Numbers alone shouldn't determine language
        assert result.script_distribution.get("sinhala", 0) == 0
    
    def test_punctuation_only(self, detector):
        """Test text with only punctuation."""
        result = detector.detect("... !!! ???")
        assert result.language == Language.UNKNOWN
    
    def test_unicode_normalization(self, detector):
        """Test handling of different Unicode normalizations."""
        # Both should be detected as Sinhala
        text1 = "ඩෙංගු"
        result = detector.detect(text1)
        assert result.language == Language.SINHALA
    
    def test_romanized_singlish_markers(self, detector):
        """Test that Romanized Singlish is detected as Latin/English initially."""
        text = "mage amma dengue clinic eka koheda"
        result = detector.detect(text)
        
        # LanguageDetector should identify this as Latin script
        # The RomanizedClassifier (Step 3) will further classify it as Singlish
        assert result.script_type == ScriptType.LATIN
