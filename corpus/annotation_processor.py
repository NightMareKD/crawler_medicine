"""
Annotation Processor

Orchestrates the complete annotation pipeline:
1. Language Detection
2. Romanized Classification
3. Text Preprocessing
4. Entity Extraction
5. Intent Classification
6. Domain Tagging
7. Q&A Generation (optional)
8. Store annotations to Supabase
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

from corpus.language_detector import LanguageDetector, LanguageResult
from corpus.romanized_classifier import RomanizedClassifier, RomanizedResult
from corpus.text_preprocessor import TextPreprocessor, PreprocessingResult
from corpus.entity_extractor import HealthEntityExtractor, ExtractionResult
from corpus.intent_classifier import HealthIntentClassifier, IntentResult
from corpus.domain_tagger import HealthDomainTagger, DomainResult
from corpus.qa_generator import QAGenerator, QAPair

logger = logging.getLogger(__name__)


@dataclass
class AnnotationResult:
    """Complete annotation result for a document."""
    context_id: str
    
    # Language analysis
    language: Optional[LanguageResult] = None
    romanized: Optional[RomanizedResult] = None
    
    # Text processing
    preprocessing: Optional[PreprocessingResult] = None
    
    # NLP annotations
    entities: Optional[ExtractionResult] = None
    intent: Optional[IntentResult] = None
    domain: Optional[DomainResult] = None
    
    # Generated Q&A
    qa_pairs: List[QAPair] = field(default_factory=list)
    
    # Processing metadata
    processing_time_ms: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "context_id": self.context_id,
            "detected_language": self.language.language.value if self.language else None,
            "language_confidence": self.language.confidence if self.language else None,
            "is_romanized": self.romanized.classification.value != "pure_english" if self.romanized else False,
            "romanized_type": self.romanized.classification.value if self.romanized else None,
            "entities": [e.to_dict() for e in self.entities.entities] if self.entities else [],
            "intent": self.intent.intent.value if self.intent else None,
            "domain": self.domain.primary_domain.value if self.domain else None,
            "qa_pairs_count": len(self.qa_pairs),
            "pii_removed": self.preprocessing.pii_removed if self.preprocessing else False,
        }


class AnnotationProcessor:
    """
    Orchestrates the complete annotation pipeline.
    """
    
    def __init__(
        self,
        language_detector: Optional[LanguageDetector] = None,
        romanized_classifier: Optional[RomanizedClassifier] = None,
        preprocessor: Optional[TextPreprocessor] = None,
        entity_extractor: Optional[HealthEntityExtractor] = None,
        intent_classifier: Optional[HealthIntentClassifier] = None,
        domain_tagger: Optional[HealthDomainTagger] = None,
        qa_generator: Optional[QAGenerator] = None,
    ):
        """Initialize with optional custom components."""
        self.language_detector = language_detector or LanguageDetector()
        self.romanized_classifier = romanized_classifier or RomanizedClassifier()
        self.preprocessor = preprocessor or TextPreprocessor()
        self.entity_extractor = entity_extractor or HealthEntityExtractor()
        self.intent_classifier = intent_classifier or HealthIntentClassifier()
        self.domain_tagger = domain_tagger or HealthDomainTagger()
        self.qa_generator = qa_generator or QAGenerator()
    
    def process(
        self,
        text: str,
        context_id: str,
        source_url: Optional[str] = None,
        generate_qa: bool = True
    ) -> AnnotationResult:
        """
        Run the complete annotation pipeline.
        
        Args:
            text: Input text to annotate
            context_id: Document context ID
            source_url: Source URL for provenance
            generate_qa: Whether to generate Q&A pairs
            
        Returns:
            AnnotationResult with all annotations
        """
        import time
        start_time = time.time()
        
        result = AnnotationResult(context_id=context_id)
        errors = []
        
        try:
            # 1. Language Detection
            result.language = self.language_detector.detect(text)
            language = result.language.language.value
            
            # 2. Romanized Classification (for Latin script)
            if result.language.script_type.value == "latin":
                result.romanized = self.romanized_classifier.classify(text)
            
            # 3. Text Preprocessing
            result.preprocessing = self.preprocessor.preprocess(text, language)
            cleaned_text = result.preprocessing.cleaned_text
            
            # 4. Entity Extraction
            result.entities = self.entity_extractor.extract(cleaned_text, language)
            
            # 5. Intent Classification
            result.intent = self.intent_classifier.classify(cleaned_text)
            
            # 6. Domain Tagging
            result.domain = self.domain_tagger.tag(cleaned_text)
            
            # 7. Q&A Generation (optional)
            if generate_qa and result.entities:
                entity_dicts = [e.to_dict() for e in result.entities.entities]
                result.qa_pairs = self.qa_generator.generate_from_content(
                    text=cleaned_text,
                    entities=entity_dicts,
                    source_url=source_url,
                    source_context_id=context_id
                )
                
                # Add intent and domain to Q&A pairs
                for qa in result.qa_pairs:
                    if not qa.intent and result.intent:
                        qa.intent = result.intent.intent.value
                    if not qa.domain and result.domain:
                        qa.domain = result.domain.primary_domain.value
        
        except Exception as e:
            logger.error(f"Annotation error for {context_id}: {e}")
            errors.append(str(e))
        
        result.errors = errors
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        return result
    
    def process_batch(
        self,
        items: List[Dict[str, Any]],
        generate_qa: bool = True
    ) -> List[AnnotationResult]:
        """
        Process multiple documents.
        
        Args:
            items: List of dicts with 'text', 'context_id', 'source_url'
            generate_qa: Whether to generate Q&A pairs
            
        Returns:
            List of AnnotationResult objects
        """
        results = []
        
        for item in items:
            result = self.process(
                text=item.get("text", ""),
                context_id=item.get("context_id", ""),
                source_url=item.get("source_url"),
                generate_qa=generate_qa
            )
            results.append(result)
        
        return results
    
    def save_to_supabase(
        self,
        result: AnnotationResult,
        repo: Any  # SupabaseRepo instance
    ) -> None:
        """
        Save annotation results to Supabase.
        
        Args:
            result: Annotation result to save
            repo: SupabaseRepo instance
        """
        context_id = result.context_id
        
        # Update language annotation
        if result.language:
            is_romanized = False
            romanized_type = None
            
            if result.romanized:
                rom_class = result.romanized.classification.value
                is_romanized = rom_class not in ("pure_english", "unknown")
                romanized_type = rom_class if is_romanized else None
            
            repo.update_language_annotation(
                context_id=context_id,
                detected_language=result.language.language.value,
                language_confidence=result.language.confidence,
                is_romanized=is_romanized,
                romanized_type=romanized_type
            )
        
        # Update entities
        if result.entities and result.entities.entities:
            entity_dicts = [e.to_dict() for e in result.entities.entities]
            repo.update_entities(context_id, entity_dicts)
        
        # Update intent and domain
        intent_val = result.intent.intent.value if result.intent else None
        domain_val = result.domain.primary_domain.value if result.domain else None
        repo.update_intent_domain(context_id, intent_val, domain_val)
        
        # Save Q&A pairs
        for qa in result.qa_pairs:
            repo.insert_qa_pair(qa.to_dict())
        
        logger.info(f"Saved annotations for {context_id}: "
                   f"{len(result.entities.entities) if result.entities else 0} entities, "
                   f"{len(result.qa_pairs)} Q&A pairs")


# Convenience function
def annotate_text(
    text: str,
    context_id: str,
    source_url: Optional[str] = None
) -> AnnotationResult:
    """Convenience function to run annotation pipeline."""
    processor = AnnotationProcessor()
    return processor.process(text, context_id, source_url)
