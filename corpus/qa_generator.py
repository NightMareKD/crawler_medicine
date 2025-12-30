"""
Q&A Pair Generator

Generates question-answer pairs from health content:
- Extracts Q&A from FAQ pages
- Generates synthetic Q&A from content
- Creates multilingual versions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


@dataclass
class QAPair:
    """A question-answer pair."""
    id: str
    question: str
    answer: str
    question_language: str = "english"
    answer_language: str = "english"
    is_romanized: bool = False
    romanized_type: Optional[str] = None
    intent: Optional[str] = None
    domain: Optional[str] = None
    entities: List[Dict[str, Any]] = field(default_factory=list)
    source_url: Optional[str] = None
    source_context_id: Optional[str] = None
    confidence: float = 1.0
    verified: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "id": self.id,
            "question_text": self.question,
            "answer_text": self.answer,
            "question_language": self.question_language,
            "answer_language": self.answer_language,
            "question_is_romanized": self.is_romanized,
            "question_romanized_type": self.romanized_type,
            "intent": self.intent,
            "domain": self.domain,
            "entities": self.entities,
            "source_url": self.source_url,
            "source_context_id": self.source_context_id,
            "verified": self.verified,
        }


class QAGenerator:
    """
    Generates Q&A pairs from health content.
    """
    
    # FAQ patterns to detect Q&A in HTML/text
    FAQ_PATTERNS = [
        # HTML patterns
        r'<(?:h\d|strong|b)[^>]*>\s*(?:Q[:.]\s*)?(.+?)\s*</(?:h\d|strong|b)>\s*<(?:p|div)[^>]*>\s*(?:A[:.]\s*)?(.+?)\s*</(?:p|div)>',
        # Plain text patterns
        r'(?:Q[:.]\s*|Question[:.]\s*)(.+?)[\n\r]+(?:A[:.]\s*|Answer[:.]\s*)(.+?)(?=\n\n|\Z)',
        # Numbered Q&A
        r'(?:\d+[.)]\s*)(.+\?)\s*[\n\r]+(.+?)(?=\d+[.)]|\n\n|\Z)',
    ]
    
    # Question generation templates
    QUESTION_TEMPLATES = {
        "location": [
            "Where is the {entity}?",
            "How to get to {entity}?",
            "What is the address of {entity}?",
        ],
        "time": [
            "What are the opening hours of {entity}?",
            "When does {entity} open?",
            "What time does {entity} close?",
        ],
        "contact": [
            "What is the phone number of {entity}?",
            "How to contact {entity}?",
        ],
        "symptoms": [
            "What are the symptoms of {entity}?",
            "How do I know if I have {entity}?",
        ],
        "treatment": [
            "How is {entity} treated?",
            "What is the treatment for {entity}?",
        ],
    }
    
    def __init__(self):
        """Initialize the generator."""
        self._faq_patterns = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in self.FAQ_PATTERNS]
    
    def extract_from_faq(self, text: str, source_url: Optional[str] = None) -> List[QAPair]:
        """
        Extract Q&A pairs from FAQ-formatted text.
        
        Args:
            text: Input text (may contain HTML)
            source_url: Source URL for provenance
            
        Returns:
            List of QAPair objects
        """
        pairs = []
        
        for pattern in self._faq_patterns:
            matches = pattern.findall(text)
            for match in matches:
                if len(match) >= 2:
                    question = self._clean_text(match[0])
                    answer = self._clean_text(match[1])
                    
                    if question and answer and len(question) > 10 and len(answer) > 10:
                        pairs.append(QAPair(
                            id=str(uuid4()),
                            question=question,
                            answer=answer,
                            source_url=source_url,
                            confidence=0.8
                        ))
        
        return pairs
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def generate_from_entities(
        self,
        entities: List[Dict[str, Any]],
        context_text: str,
        source_context_id: Optional[str] = None
    ) -> List[QAPair]:
        """
        Generate Q&A pairs from extracted entities.
        
        Args:
            entities: List of entity dictionaries
            context_text: Original text for context
            source_context_id: Source context ID
            
        Returns:
            List of generated QAPair objects
        """
        pairs = []
        
        for entity in entities:
            entity_type = entity.get("type", "")
            entity_text = entity.get("text", "")
            normalized = entity.get("normalized", entity_text)
            
            if not entity_text:
                continue
            
            # Generate questions based on entity type
            if entity_type in ("hospital", "clinic"):
                # Location questions
                for template in self.QUESTION_TEMPLATES.get("location", [])[:1]:
                    question = template.format(entity=normalized)
                    answer = self._find_answer_in_context(context_text, entity_text, "location")
                    
                    if answer:
                        pairs.append(QAPair(
                            id=str(uuid4()),
                            question=question,
                            answer=answer,
                            source_context_id=source_context_id,
                            intent="asking_location",
                            confidence=0.6
                        ))
                
                # Time questions
                for template in self.QUESTION_TEMPLATES.get("time", [])[:1]:
                    question = template.format(entity=normalized)
                    answer = self._find_answer_in_context(context_text, entity_text, "time")
                    
                    if answer:
                        pairs.append(QAPair(
                            id=str(uuid4()),
                            question=question,
                            answer=answer,
                            source_context_id=source_context_id,
                            intent="asking_time",
                            confidence=0.6
                        ))
            
            elif entity_type == "disease":
                # Symptoms questions
                for template in self.QUESTION_TEMPLATES.get("symptoms", [])[:1]:
                    question = template.format(entity=normalized)
                    answer = self._find_answer_in_context(context_text, entity_text, "symptoms")
                    
                    if answer:
                        pairs.append(QAPair(
                            id=str(uuid4()),
                            question=question,
                            answer=answer,
                            source_context_id=source_context_id,
                            intent="asking_symptoms",
                            domain=entity_text.lower(),
                            confidence=0.6
                        ))
        
        return pairs
    
    def _find_answer_in_context(
        self,
        context: str,
        entity: str,
        answer_type: str
    ) -> Optional[str]:
        """
        Find an answer for the entity in context text.
        
        This is a simple extraction - in a full implementation,
        you'd use more sophisticated NLP.
        """
        # Find sentences containing the entity
        sentences = re.split(r'[.!?]', context)
        
        for sentence in sentences:
            if entity.lower() in sentence.lower():
                sentence = sentence.strip()
                if len(sentence) > 20:
                    return sentence + "."
        
        return None
    
    def create_multilingual_qa(
        self,
        qa: QAPair,
        translator: Any  # NLLBTranslator instance
    ) -> List[QAPair]:
        """
        Create translated versions of a Q&A pair.
        
        Args:
            qa: Original Q&A pair
            translator: Translator instance
            
        Returns:
            List of Q&A pairs in different languages
        """
        pairs = [qa]  # Include original
        
        target_languages = ["sinhala", "tamil"]
        if qa.question_language != "english":
            target_languages.append("english")
        
        for target_lang in target_languages:
            if target_lang == qa.question_language:
                continue
            
            try:
                # Translate question
                q_result = translator.translate(
                    qa.question,
                    qa.question_language,
                    target_lang
                )
                
                # Translate answer
                a_result = translator.translate(
                    qa.answer,
                    qa.answer_language,
                    target_lang
                )
                
                pairs.append(QAPair(
                    id=str(uuid4()),
                    question=q_result.translated_text,
                    answer=a_result.translated_text,
                    question_language=target_lang,
                    answer_language=target_lang,
                    intent=qa.intent,
                    domain=qa.domain,
                    source_context_id=qa.source_context_id,
                    confidence=qa.confidence * 0.9  # Slightly lower for translations
                ))
            except Exception as e:
                logger.warning(f"Failed to translate Q&A to {target_lang}: {e}")
        
        return pairs
    
    def generate_from_content(
        self,
        text: str,
        entities: Optional[List[Dict[str, Any]]] = None,
        source_url: Optional[str] = None,
        source_context_id: Optional[str] = None
    ) -> List[QAPair]:
        """
        Generate Q&A pairs from content using multiple strategies.
        
        Args:
            text: Input text
            entities: Pre-extracted entities (optional)
            source_url: Source URL
            source_context_id: Source context ID
            
        Returns:
            List of QAPair objects
        """
        all_pairs = []
        
        # Try FAQ extraction first
        faq_pairs = self.extract_from_faq(text, source_url)
        all_pairs.extend(faq_pairs)
        
        # Generate from entities if provided
        if entities:
            entity_pairs = self.generate_from_entities(
                entities, text, source_context_id
            )
            all_pairs.extend(entity_pairs)
        
        # Deduplicate by question similarity
        seen_questions = set()
        unique_pairs = []
        
        for pair in all_pairs:
            q_normalized = pair.question.lower().strip()
            if q_normalized not in seen_questions:
                seen_questions.add(q_normalized)
                unique_pairs.append(pair)
        
        return unique_pairs


# Convenience function
def generate_qa_pairs(
    text: str,
    entities: Optional[List[Dict[str, Any]]] = None,
    source_url: Optional[str] = None
) -> List[QAPair]:
    """Convenience function to generate Q&A pairs."""
    generator = QAGenerator()
    return generator.generate_from_content(text, entities, source_url)
