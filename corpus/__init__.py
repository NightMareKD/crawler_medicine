"""
Corpus Processing Package
Multilingual health corpus annotation and processing modules.
"""

from corpus.language_detector import LanguageDetector, Language, LanguageResult
from corpus.romanized_classifier import RomanizedClassifier, RomanizedType, RomanizedResult
from corpus.text_preprocessor import TextPreprocessor, PreprocessingResult
from corpus.entity_extractor import HealthEntityExtractor, Entity, ExtractionResult
from corpus.intent_classifier import HealthIntentClassifier, Intent, IntentResult
from corpus.domain_tagger import HealthDomainTagger, HealthDomain, DomainResult
from corpus.qa_generator import QAGenerator, QAPair
from corpus.annotation_processor import AnnotationProcessor, AnnotationResult
from corpus.bias_auditor import BiasAuditor, BiasReport
from corpus.deduplicator import ContentDeduplicator

__all__ = [
    # Language Detection
    "LanguageDetector",
    "Language",
    "LanguageResult",
    # Romanized Classification
    "RomanizedClassifier",
    "RomanizedType",
    "RomanizedResult",
    # Text Preprocessing
    "TextPreprocessor",
    "PreprocessingResult",
    # Entity Extraction
    "HealthEntityExtractor",
    "Entity",
    "ExtractionResult",
    # Intent Classification
    "HealthIntentClassifier",
    "Intent",
    "IntentResult",
    # Domain Tagging
    "HealthDomainTagger",
    "HealthDomain",
    "DomainResult",
    # Q&A Generation
    "QAGenerator",
    "QAPair",
    # Annotation Processing
    "AnnotationProcessor",
    "AnnotationResult",
    # Bias Auditing
    "BiasAuditor",
    "BiasReport",
    # Deduplication
    "ContentDeduplicator",
]

