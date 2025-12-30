"""
Intent Classification Module

Classifies health-related query intents:
- asking_location: Where is the clinic?
- asking_time: What time does it open?
- asking_symptoms: What are dengue symptoms?
- asking_treatment: How to treat fever?
- asking_appointment: How to book?
- asking_contact: Phone number?
- general_info: Tell me about...
- emergency: Urgent help
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    """Health query intents."""
    ASKING_LOCATION = "asking_location"
    ASKING_TIME = "asking_time"
    ASKING_SYMPTOMS = "asking_symptoms"
    ASKING_TREATMENT = "asking_treatment"
    ASKING_APPOINTMENT = "asking_appointment"
    ASKING_CONTACT = "asking_contact"
    GENERAL_INFO = "general_info"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: Intent
    confidence: float
    matched_patterns: List[str]
    secondary_intents: List[Tuple[Intent, float]] = None
    
    def __post_init__(self):
        if self.secondary_intents is None:
            self.secondary_intents = []


class HealthIntentClassifier:
    """
    Classifies health-related query intents using pattern matching.
    
    Supports English, Singlish, and Tamilish patterns.
    """
    
    # Intent patterns (English)
    PATTERNS = {
        Intent.ASKING_LOCATION: [
            r'\b(?:where|koheda|enga|location|address|directions?)\b',
            r'\b(?:which|nearest|closest|nearby)\s+(?:hospital|clinic)\b',
            r'\b(?:how\s+to\s+(?:get|go|reach))\b',
        ],
        Intent.ASKING_TIME: [
            r'\b(?:what\s+time|when|keeyatada|eppo|hours?|schedule)\b',
            r'\b(?:open|close|opening|closing)\s*(?:time|hours?)?\b',
            r'\b(?:morning|afternoon|evening|weekday|weekend)\b',
        ],
        Intent.ASKING_SYMPTOMS: [
            r'\b(?:symptom|signs?|indication)\b',
            r'\b(?:what\s+(?:are|is)\s+the\s+symptoms?)\b',
            r'\b(?:how\s+(?:do\s+i|to)\s+know\s+if)\b',
            r'\b(?:feel(?:ing)?|suffering|experiencing)\b',
        ],
        Intent.ASKING_TREATMENT: [
            r'\b(?:treatment|treat|cure|remedy|medicine)\b',
            r'\b(?:how\s+to\s+(?:treat|cure|heal))\b',
            r'\b(?:what\s+(?:medicine|medication|drug))\b',
            r'\b(?:should\s+i\s+(?:take|use|do))\b',
        ],
        Intent.ASKING_APPOINTMENT: [
            r'\b(?:appointment|book(?:ing)?|reserve|schedule)\b',
            r'\b(?:how\s+to\s+(?:book|make|get)\s+(?:an?\s+)?appointment)\b',
            r'\b(?:register|registration|enroll)\b',
        ],
        Intent.ASKING_CONTACT: [
            r'\b(?:phone|telephone|call|contact|number|hotline)\b',
            r'\b(?:email|fax|mobile)\b',
            r'\b(?:how\s+to\s+(?:contact|call|reach))\b',
        ],
        Intent.EMERGENCY: [
            r'\b(?:emergency|urgent|immediately|ambulance)\b',
            r'\b(?:help|911|1990)\b',  # 1990 is Sri Lanka emergency
            r'\b(?:dying|critical|serious(?:ly)?|severe)\b',
            r'\b(?:accident|bleeding|unconscious|chest\s+pain)\b',
        ],
        Intent.GENERAL_INFO: [
            r'\b(?:what\s+is|tell\s+me|information|about|explain)\b',
            r'\b(?:learn|know|understand)\b',
        ],
    }
    
    # Singlish patterns
    SINGLISH_PATTERNS = {
        Intent.ASKING_LOCATION: [
            r'\b(?:koheda|kohomada\s+yanne)\b',
            r'\b(?:hospital\s+eka|clinic\s+eka)\s+koheda\b',
        ],
        Intent.ASKING_TIME: [
            r'\b(?:keeyatada|keeyata)\b',
            r'\b(?:kawadada|kavadada)\b',
        ],
        Intent.ASKING_SYMPTOMS: [
            r'\b(?:lakshana|roga\s+lakshana)\b',
        ],
        Intent.ASKING_APPOINTMENT: [
            r'\b(?:appointment\s+ganna|book\s+karanna)\b',
        ],
    }
    
    # Tamilish patterns
    TAMILISH_PATTERNS = {
        Intent.ASKING_LOCATION: [
            r'\b(?:enga\s+irukku|enga)\b',
        ],
        Intent.ASKING_TIME: [
            r'\b(?:eppo|eppadi|evlo\s+neram)\b',
        ],
    }
    
    def __init__(self):
        """Initialize the classifier with compiled patterns."""
        self._compiled_patterns: Dict[Intent, List[re.Pattern]] = {}
        
        # Compile all patterns
        for intent, patterns in self.PATTERNS.items():
            self._compiled_patterns[intent] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
        
        # Add Singlish patterns
        for intent, patterns in self.SINGLISH_PATTERNS.items():
            if intent not in self._compiled_patterns:
                self._compiled_patterns[intent] = []
            self._compiled_patterns[intent].extend([
                re.compile(p, re.IGNORECASE) for p in patterns
            ])
        
        # Add Tamilish patterns
        for intent, patterns in self.TAMILISH_PATTERNS.items():
            if intent not in self._compiled_patterns:
                self._compiled_patterns[intent] = []
            self._compiled_patterns[intent].extend([
                re.compile(p, re.IGNORECASE) for p in patterns
            ])
    
    def classify(self, text: str) -> IntentResult:
        """
        Classify the intent of a text query.
        
        Args:
            text: Input text
            
        Returns:
            IntentResult with primary and secondary intents
        """
        if not text or not text.strip():
            return IntentResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                matched_patterns=[]
            )
        
        scores: Dict[Intent, Tuple[float, List[str]]] = {}
        
        # Check each intent's patterns
        for intent, patterns in self._compiled_patterns.items():
            matched = []
            for pattern in patterns:
                if pattern.search(text):
                    matched.append(pattern.pattern)
            
            if matched:
                # Score based on number of matches and pattern specificity
                score = min(len(matched) * 0.3 + 0.4, 1.0)
                scores[intent] = (score, matched)
        
        if not scores:
            # Default to general info for informational queries
            if re.search(r'\?', text):
                return IntentResult(
                    intent=Intent.GENERAL_INFO,
                    confidence=0.3,
                    matched_patterns=["question_mark"]
                )
            return IntentResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                matched_patterns=[]
            )
        
        # Find primary intent
        sorted_intents = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
        primary_intent, (primary_score, primary_patterns) = sorted_intents[0]
        
        # Get secondary intents
        secondary = [
            (intent, score) 
            for intent, (score, _) in sorted_intents[1:3]
            if score > 0.3
        ]
        
        return IntentResult(
            intent=primary_intent,
            confidence=primary_score,
            matched_patterns=primary_patterns,
            secondary_intents=secondary
        )
    
    def classify_batch(self, texts: List[str]) -> List[IntentResult]:
        """Classify multiple texts."""
        return [self.classify(text) for text in texts]
    
    def get_intent_examples(self, intent: Intent) -> List[str]:
        """Get example queries for an intent."""
        examples = {
            Intent.ASKING_LOCATION: [
                "Where is the dengue clinic?",
                "mage amma dengue clinic eka koheda",
                "Colombo hospital enga irukku",
            ],
            Intent.ASKING_TIME: [
                "What time does the OPD open?",
                "clinic eka keeyatada",
                "hospital eppo close",
            ],
            Intent.ASKING_SYMPTOMS: [
                "What are the symptoms of dengue?",
                "How do I know if I have fever?",
            ],
            Intent.ASKING_TREATMENT: [
                "How to treat dengue at home?",
                "What medicine should I take for fever?",
            ],
            Intent.ASKING_APPOINTMENT: [
                "How to book an appointment?",
                "appointment ganna kohomada",
            ],
            Intent.ASKING_CONTACT: [
                "What is the hospital phone number?",
                "Contact number for emergency?",
            ],
            Intent.EMERGENCY: [
                "Emergency! Need ambulance now!",
                "My child is having severe fever",
            ],
            Intent.GENERAL_INFO: [
                "Tell me about dengue prevention",
                "What is COVID-19?",
            ],
        }
        return examples.get(intent, [])


# Convenience function
def classify_intent(text: str) -> IntentResult:
    """Convenience function for intent classification."""
    classifier = HealthIntentClassifier()
    return classifier.classify(text)
