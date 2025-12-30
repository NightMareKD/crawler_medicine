"""
Health Domain Entity Extractor

Extracts health-related entities from text:
- Hospitals and clinics (Sri Lanka specific)
- Diseases and conditions
- Symptoms
- Medicines
- Dates and times
- Locations

Uses gazette-based matching combined with pattern recognition.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """Types of health entities."""
    HOSPITAL = "hospital"
    CLINIC = "clinic"
    DISEASE = "disease"
    SYMPTOM = "symptom"
    MEDICINE = "medicine"
    DOCTOR = "doctor"
    LOCATION = "location"
    TIME = "time"
    DATE = "date"
    PHONE = "phone"
    ORGANIZATION = "organization"


@dataclass
class Entity:
    """An extracted entity."""
    entity_type: EntityType
    text: str
    normalized_text: Optional[str] = None
    start: int = 0
    end: int = 0
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.entity_type.value,
            "text": self.text,
            "normalized": self.normalized_text,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


@dataclass 
class ExtractionResult:
    """Result of entity extraction."""
    entities: List[Entity] = field(default_factory=list)
    entity_counts: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entities": [e.to_dict() for e in self.entities],
            "counts": self.entity_counts
        }


class HealthEntityExtractor:
    """
    Extracts health domain entities from multilingual text.
    
    Uses:
    - Gazette-based matching for Sri Lankan hospitals, diseases, etc.
    - Pattern matching for times, dates, phone numbers
    - Fuzzy matching for variations
    """
    
    # Time patterns
    TIME_PATTERNS = [
        r'\b\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)?\b',  # 8:00 AM
        r'\b\d{1,2}\s*(?:am|pm|AM|PM)\b',          # 8am
        r'\b(?:morning|afternoon|evening|night)\b',
    ]
    
    # Date patterns
    DATE_PATTERNS = [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',     # DD/MM/YYYY
        r'\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
        r'\b(?:weekday|weekend)s?\b',
    ]
    
    # Phone patterns (Sri Lankan)
    PHONE_PATTERNS = [
        r'\b0\d{9}\b',
        r'\b\+94\s?\d{9}\b',
    ]
    
    def __init__(self, gazettes_path: Optional[Path] = None):
        """
        Initialize the extractor.
        
        Args:
            gazettes_path: Path to health_entities.json gazette file
        """
        self.hospitals: Dict[str, Dict] = {}
        self.diseases: Dict[str, Dict] = {}
        self.symptoms: Dict[str, Dict] = {}
        self.clinics: Dict[str, Dict] = {}
        
        # Build lookup dictionaries
        self._hospital_aliases: Dict[str, str] = {}
        self._disease_aliases: Dict[str, str] = {}
        self._symptom_aliases: Dict[str, str] = {}
        self._clinic_aliases: Dict[str, str] = {}
        
        # Load gazettes
        if gazettes_path is None:
            gazettes_path = Path(__file__).parent / "gazettes" / "health_entities.json"
        
        if gazettes_path.exists():
            self._load_gazettes(gazettes_path)
        else:
            logger.warning(f"Gazette file not found: {gazettes_path}")
            self._load_default_gazettes()
        
        # Compile patterns
        self._time_patterns = [re.compile(p, re.IGNORECASE) for p in self.TIME_PATTERNS]
        self._date_patterns = [re.compile(p, re.IGNORECASE) for p in self.DATE_PATTERNS]
        self._phone_patterns = [re.compile(p) for p in self.PHONE_PATTERNS]
    
    def _load_gazettes(self, path: Path) -> None:
        """Load gazette data from JSON file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load hospitals
            for hospital in data.get("hospitals", []):
                name = hospital["name"]
                self.hospitals[name.lower()] = hospital
                for alias in hospital.get("aliases", []):
                    self._hospital_aliases[alias.lower()] = name
            
            # Load diseases
            for disease in data.get("diseases", []):
                name = disease["name"]
                self.diseases[name.lower()] = disease
                for alias in disease.get("aliases", []):
                    self._disease_aliases[alias.lower()] = name
            
            # Load symptoms
            for symptom in data.get("symptoms", []):
                name = symptom["name"]
                self.symptoms[name.lower()] = symptom
                for alias in symptom.get("aliases", []):
                    self._symptom_aliases[alias.lower()] = name
            
            # Load clinics
            for clinic in data.get("clinics", []):
                name = clinic["name"]
                self.clinics[name.lower()] = clinic
                for alias in clinic.get("aliases", []):
                    self._clinic_aliases[alias.lower()] = name
            
            logger.info(f"Loaded gazettes: {len(self.hospitals)} hospitals, "
                       f"{len(self.diseases)} diseases, {len(self.symptoms)} symptoms")
            
        except Exception as e:
            logger.error(f"Failed to load gazettes: {e}")
            self._load_default_gazettes()
    
    def _load_default_gazettes(self) -> None:
        """Load minimal default gazettes."""
        # Default hospitals
        self.hospitals = {
            "national hospital of sri lanka": {"name": "National Hospital of Sri Lanka", "location": "Colombo"},
        }
        self._hospital_aliases = {"national hospital": "National Hospital of Sri Lanka"}
        
        # Default diseases
        self.diseases = {
            "dengue fever": {"name": "Dengue Fever"},
            "covid-19": {"name": "COVID-19"},
        }
        self._disease_aliases = {"dengue": "Dengue Fever", "covid": "COVID-19", "corona": "COVID-19"}
    
    def _find_gazette_matches(
        self,
        text: str,
        gazettes: Dict[str, Dict],
        aliases: Dict[str, str],
        entity_type: EntityType
    ) -> List[Entity]:
        """Find matches from gazette data."""
        entities = []
        text_lower = text.lower()
        
        # Search for aliases first (usually shorter, more common)
        for alias, canonical in aliases.items():
            # Use word boundary matching
            pattern = r'\b' + re.escape(alias) + r'\b'
            for match in re.finditer(pattern, text_lower):
                entities.append(Entity(
                    entity_type=entity_type,
                    text=text[match.start():match.end()],
                    normalized_text=canonical,
                    start=match.start(),
                    end=match.end(),
                    confidence=0.9,
                    metadata=gazettes.get(canonical.lower(), {})
                ))
        
        # Search for canonical names
        for name, data in gazettes.items():
            if name in text_lower:
                start = text_lower.find(name)
                entities.append(Entity(
                    entity_type=entity_type,
                    text=text[start:start+len(name)],
                    normalized_text=data.get("name", name),
                    start=start,
                    end=start + len(name),
                    confidence=1.0,
                    metadata=data
                ))
        
        return entities
    
    def _find_pattern_matches(
        self,
        text: str,
        patterns: List[re.Pattern],
        entity_type: EntityType
    ) -> List[Entity]:
        """Find matches using regex patterns."""
        entities = []
        
        for pattern in patterns:
            for match in pattern.finditer(text):
                entities.append(Entity(
                    entity_type=entity_type,
                    text=match.group(),
                    start=match.start(),
                    end=match.end(),
                    confidence=0.95
                ))
        
        return entities
    
    def extract(self, text: str, language: str = "english") -> ExtractionResult:
        """
        Extract entities from text.
        
        Args:
            text: Input text
            language: Source language
            
        Returns:
            ExtractionResult with extracted entities
        """
        if not text:
            return ExtractionResult()
        
        all_entities = []
        
        # Extract hospitals
        all_entities.extend(self._find_gazette_matches(
            text, self.hospitals, self._hospital_aliases, EntityType.HOSPITAL
        ))
        
        # Extract diseases
        all_entities.extend(self._find_gazette_matches(
            text, self.diseases, self._disease_aliases, EntityType.DISEASE
        ))
        
        # Extract symptoms
        all_entities.extend(self._find_gazette_matches(
            text, self.symptoms, self._symptom_aliases, EntityType.SYMPTOM
        ))
        
        # Extract clinics
        all_entities.extend(self._find_gazette_matches(
            text, self.clinics, self._clinic_aliases, EntityType.CLINIC
        ))
        
        # Extract times
        all_entities.extend(self._find_pattern_matches(
            text, self._time_patterns, EntityType.TIME
        ))
        
        # Extract dates
        all_entities.extend(self._find_pattern_matches(
            text, self._date_patterns, EntityType.DATE
        ))
        
        # Extract phone numbers
        all_entities.extend(self._find_pattern_matches(
            text, self._phone_patterns, EntityType.PHONE
        ))
        
        # Deduplicate overlapping entities (keep higher confidence)
        all_entities = self._deduplicate_entities(all_entities)
        
        # Count by type
        counts = {}
        for entity in all_entities:
            counts[entity.entity_type.value] = counts.get(entity.entity_type.value, 0) + 1
        
        return ExtractionResult(
            entities=all_entities,
            entity_counts=counts
        )
    
    def _deduplicate_entities(self, entities: List[Entity]) -> List[Entity]:
        """Remove overlapping entities, keeping higher confidence ones."""
        if not entities:
            return []
        
        # Sort by start position, then by confidence (descending)
        sorted_entities = sorted(entities, key=lambda e: (e.start, -e.confidence))
        
        result = []
        last_end = -1
        
        for entity in sorted_entities:
            if entity.start >= last_end:
                result.append(entity)
                last_end = entity.end
        
        return result
    
    def extract_batch(
        self,
        texts: List[str],
        language: str = "english"
    ) -> List[ExtractionResult]:
        """Extract entities from multiple texts."""
        return [self.extract(text, language) for text in texts]
    
    def get_entity_summary(self, result: ExtractionResult) -> Dict[str, List[str]]:
        """
        Get a summary of extracted entities grouped by type.
        
        Args:
            result: Extraction result
            
        Returns:
            Dict mapping entity types to lists of entity texts
        """
        summary = {}
        for entity in result.entities:
            type_name = entity.entity_type.value
            if type_name not in summary:
                summary[type_name] = []
            
            text = entity.normalized_text or entity.text
            if text not in summary[type_name]:
                summary[type_name].append(text)
        
        return summary


# Convenience function
def extract_entities(text: str, language: str = "english") -> ExtractionResult:
    """Convenience function for entity extraction."""
    extractor = HealthEntityExtractor()
    return extractor.extract(text, language)
