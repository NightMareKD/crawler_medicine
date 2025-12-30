"""
Translation Engine using NLLB-200

Provides translation between Sinhala, Tamil, and English using
Meta's No Language Left Behind (NLLB-200) model.

Supports GPU acceleration for faster inference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
import logging

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """Result of a translation operation."""
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    confidence: Optional[float] = None
    model_name: str = "nllb-200"


class NLLBTranslator:
    """
    Translation using Meta's NLLB-200 model.
    
    Supports:
    - Sinhala (sin_Sinh)
    - Tamil (tam_Taml)
    - English (eng_Latn)
    
    Uses GPU by default if available.
    """
    
    # Model variants (distilled for efficiency)
    MODEL_VARIANTS = {
        "small": "facebook/nllb-200-distilled-600M",
        "medium": "facebook/nllb-200-1.3B",
        "large": "facebook/nllb-200-3.3B"
    }
    
    DEFAULT_MODEL = "facebook/nllb-200-distilled-600M"
    
    # NLLB language codes
    LANG_CODES = {
        "sinhala": "sin_Sinh",
        "tamil": "tam_Taml",
        "english": "eng_Latn",
        # Aliases
        "si": "sin_Sinh",
        "ta": "tam_Taml",
        "en": "eng_Latn",
    }
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        device: str = "auto",
        max_length: int = 512,
        load_on_init: bool = False
    ):
        """
        Initialize the translator.
        
        Args:
            model_name: NLLB model name or size ('small', 'medium', 'large')
            device: Device to use ('auto', 'cuda', 'cpu')
            max_length: Maximum sequence length for translation
            load_on_init: Whether to load model immediately
        """
        # Resolve model name
        if model_name in self.MODEL_VARIANTS:
            self.model_name = self.MODEL_VARIANTS[model_name]
        else:
            self.model_name = model_name or self.DEFAULT_MODEL
        
        self.max_length = max_length
        self.device = device
        
        # Lazy loading
        self._model = None
        self._tokenizer = None
        self._actual_device = None
        
        if load_on_init:
            self._load_model()
    
    def _resolve_device(self) -> str:
        """Resolve the device to use."""
        if self.device == "auto":
            try:
                import torch
                if torch.cuda.is_available():
                    return "cuda"
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    return "mps"
                else:
                    return "cpu"
            except ImportError:
                return "cpu"
        return self.device
    
    def _load_model(self) -> None:
        """Load the translation model."""
        if self._model is not None:
            return
        
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            import torch
            
            self._actual_device = self._resolve_device()
            
            logger.info(f"Loading NLLB model: {self.model_name} on {self._actual_device}")
            
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
            
            if self._actual_device == "cuda":
                self._model = self._model.cuda()
            elif self._actual_device == "mps":
                self._model = self._model.to("mps")
            
            self._model.eval()
            
            logger.info(f"NLLB model loaded successfully on {self._actual_device}")
            
        except ImportError as e:
            raise RuntimeError(
                "Translation requires transformers and torch. "
                "Install: pip install transformers torch"
            ) from e
        except Exception as e:
            logger.error(f"Failed to load NLLB model: {e}")
            raise
    
    def _get_lang_code(self, lang: str) -> str:
        """Convert language name to NLLB code."""
        lang_lower = lang.lower()
        if lang_lower in self.LANG_CODES:
            return self.LANG_CODES[lang_lower]
        # Assume it's already a valid NLLB code
        return lang
    
    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> TranslationResult:
        """
        Translate text between languages.
        
        Args:
            text: Text to translate
            source_lang: Source language ('sinhala', 'tamil', 'english' or NLLB codes)
            target_lang: Target language
            
        Returns:
            TranslationResult with translated text
        """
        if not text or not text.strip():
            return TranslationResult(
                source_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang
            )
        
        # Ensure model is loaded
        self._load_model()
        
        import torch
        
        src_code = self._get_lang_code(source_lang)
        tgt_code = self._get_lang_code(target_lang)
        
        # Set source language for tokenizer
        self._tokenizer.src_lang = src_code
        
        # Tokenize
        inputs = self._tokenizer(
            text,
            return_tensors="pt",
            max_length=self.max_length,
            truncation=True
        )
        
        # Move to device
        if self._actual_device == "cuda":
            inputs = {k: v.cuda() for k, v in inputs.items()}
        elif self._actual_device == "mps":
            inputs = {k: v.to("mps") for k, v in inputs.items()}
        
        # Generate translation
        with torch.no_grad():
            generated = self._model.generate(
                **inputs,
                forced_bos_token_id=self._tokenizer.lang_code_to_id[tgt_code],
                max_length=self.max_length,
                num_beams=5,
                early_stopping=True
            )
        
        # Decode
        translated = self._tokenizer.batch_decode(
            generated,
            skip_special_tokens=True
        )[0]
        
        return TranslationResult(
            source_text=text,
            translated_text=translated,
            source_lang=source_lang,
            target_lang=target_lang,
            model_name=self.model_name
        )
    
    def translate_to_english(self, text: str, source_lang: str) -> TranslationResult:
        """
        Convenience method to translate to English.
        
        Args:
            text: Text to translate
            source_lang: Source language
            
        Returns:
            TranslationResult
        """
        return self.translate(text, source_lang, "english")
    
    def translate_from_english(self, text: str, target_lang: str) -> TranslationResult:
        """
        Convenience method to translate from English.
        
        Args:
            text: English text to translate
            target_lang: Target language
            
        Returns:
            TranslationResult
        """
        return self.translate(text, "english", target_lang)
    
    def translate_batch(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str
    ) -> List[TranslationResult]:
        """
        Translate multiple texts.
        
        Args:
            texts: List of texts to translate
            source_lang: Source language
            target_lang: Target language
            
        Returns:
            List of TranslationResult objects
        """
        return [
            self.translate(text, source_lang, target_lang)
            for text in texts
        ]
    
    def create_multilingual_versions(
        self,
        text: str,
        source_lang: str
    ) -> Dict[str, str]:
        """
        Create translations in all supported languages.
        
        Args:
            text: Text to translate
            source_lang: Source language
            
        Returns:
            Dict mapping language codes to translations
        """
        target_langs = ["sinhala", "tamil", "english"]
        source_lower = source_lang.lower()
        
        versions = {source_lower: text}
        
        for target in target_langs:
            if target != source_lower:
                try:
                    result = self.translate(text, source_lang, target)
                    versions[target] = result.translated_text
                except Exception as e:
                    logger.warning(f"Failed to translate to {target}: {e}")
                    versions[target] = ""
        
        return versions
    
    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None
    
    def unload(self) -> None:
        """Unload model to free memory."""
        if self._model is not None:
            del self._model
            del self._tokenizer
            self._model = None
            self._tokenizer = None
            
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            
            logger.info("NLLB model unloaded")


class MockTranslator:
    """
    Mock translator for testing without loading the actual model.
    Returns placeholder translations.
    """
    
    def __init__(self):
        self.model_name = "mock"
    
    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str
    ) -> TranslationResult:
        """Return mock translation."""
        return TranslationResult(
            source_text=text,
            translated_text=f"[{target_lang}] {text}",
            source_lang=source_lang,
            target_lang=target_lang,
            model_name="mock"
        )
    
    def translate_to_english(self, text: str, source_lang: str) -> TranslationResult:
        return self.translate(text, source_lang, "english")
    
    def translate_from_english(self, text: str, target_lang: str) -> TranslationResult:
        return self.translate(text, "english", target_lang)
    
    def translate_batch(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str
    ) -> List[TranslationResult]:
        return [self.translate(t, source_lang, target_lang) for t in texts]
    
    def create_multilingual_versions(
        self,
        text: str,
        source_lang: str
    ) -> Dict[str, str]:
        return {
            "sinhala": f"[sinhala] {text}",
            "tamil": f"[tamil] {text}",
            "english": f"[english] {text}"
        }
    
    @property
    def is_loaded(self) -> bool:
        return True
    
    def unload(self) -> None:
        pass


def get_translator(use_mock: bool = False, **kwargs) -> Union[NLLBTranslator, MockTranslator]:
    """
    Factory function to get a translator instance.
    
    Args:
        use_mock: If True, return a mock translator for testing
        **kwargs: Arguments passed to NLLBTranslator
        
    Returns:
        Translator instance
    """
    if use_mock:
        return MockTranslator()
    return NLLBTranslator(**kwargs)
