"""
Domain Tagging Module

Tags content with health domains:
- dengue, covid, vaccination, mental_health
- maternal_health, child_health, opd, emergency
- pharmacy, laboratory, general
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)


class HealthDomain(str, Enum):
    """Health domains."""
    DENGUE = "dengue"
    COVID = "covid"
    VACCINATION = "vaccination"
    MENTAL_HEALTH = "mental_health"
    MATERNAL_HEALTH = "maternal_health"
    CHILD_HEALTH = "child_health"
    OPD = "opd"
    EMERGENCY = "emergency"
    PHARMACY = "pharmacy"
    LABORATORY = "laboratory"
    DENTAL = "dental"
    EYE = "eye"
    GENERAL = "general"


@dataclass
class DomainTag:
    """A domain tag with confidence."""
    domain: HealthDomain
    confidence: float
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class DomainResult:
    """Result of domain tagging."""
    primary_domain: HealthDomain
    confidence: float
    all_domains: List[DomainTag] = field(default_factory=list)
    keywords_found: List[str] = field(default_factory=list)


class HealthDomainTagger:
    """
    Tags content with health domains using keyword matching.
    
    Supports multilingual keywords (English, Sinhala, Tamil).
    """
    
    # Domain keywords
    DOMAIN_KEYWORDS = {
        HealthDomain.DENGUE: [
            "dengue", "ඩෙංගු", "டெங்கு", "platelet", "aedes", "mosquito",
            "hemorrhagic", "fever", "DF", "DHF", "DSS"
        ],
        HealthDomain.COVID: [
            "covid", "corona", "coronavirus", "sars-cov", "කොවිඩ්",
            "quarantine", "isolation", "pcr", "antigen", "rar test",
            "booster", "pandemic", "lockdown"
        ],
        HealthDomain.VACCINATION: [
            "vaccine", "vaccination", "immunization", "immunize",
            "එන්නත්", "தடுப்பூசி", "jab", "dose", "booster",
            "mmr", "bcg", "polio", "tetanus", "hepatitis"
        ],
        HealthDomain.MENTAL_HEALTH: [
            "mental", "psychiatric", "psychology", "depression",
            "anxiety", "stress", "counseling", "therapy", "මානසික",
            "suicide", "bipolar", "schizophrenia"
        ],
        HealthDomain.MATERNAL_HEALTH: [
            "maternal", "maternity", "pregnancy", "pregnant", "antenatal",
            "postnatal", "delivery", "childbirth", "මාතෘ", "obstetric",
            "gynecology", "midwife"
        ],
        HealthDomain.CHILD_HEALTH: [
            "child", "children", "pediatric", "paediatric", "baby",
            "infant", "newborn", "toddler", "ළමා", "குழந்தை"
        ],
        HealthDomain.OPD: [
            "opd", "outpatient", "out patient", "clinic", "consultation",
            "doctor", "appointment", "checkup", "check-up"
        ],
        HealthDomain.EMERGENCY: [
            "emergency", "accident", "trauma", "ambulance", "icu",
            "critical", "urgent", "1990", "911", "casualty"
        ],
        HealthDomain.PHARMACY: [
            "pharmacy", "pharmaceutical", "medicine", "medication",
            "drug", "prescription", "beheth", "மருந்து"
        ],
        HealthDomain.LABORATORY: [
            "laboratory", "lab", "test", "blood test", "urine",
            "x-ray", "scan", "mri", "ct scan", "ultrasound"
        ],
        HealthDomain.DENTAL: [
            "dental", "dentist", "tooth", "teeth", "oral",
            "දන්ත", "பல்"
        ],
        HealthDomain.EYE: [
            "eye", "ophthalmology", "optometry", "vision", "optical",
            "ඇස්", "கண்"
        ],
    }
    
    def __init__(self):
        """Initialize the tagger with compiled patterns."""
        self._patterns: Dict[HealthDomain, List[re.Pattern]] = {}
        
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            self._patterns[domain] = [
                re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
                for kw in keywords
            ]
    
    def tag(self, text: str) -> DomainResult:
        """
        Tag text with health domains.
        
        Args:
            text: Input text
            
        Returns:
            DomainResult with primary and all matched domains
        """
        if not text:
            return DomainResult(
                primary_domain=HealthDomain.GENERAL,
                confidence=0.0
            )
        
        domain_scores: Dict[HealthDomain, List[str]] = {}
        all_keywords = []
        
        for domain, patterns in self._patterns.items():
            matched = []
            for pattern in patterns:
                if pattern.search(text):
                    matched.append(pattern.pattern.replace(r'\b', '').replace('\\', ''))
            
            if matched:
                domain_scores[domain] = matched
                all_keywords.extend(matched)
        
        if not domain_scores:
            return DomainResult(
                primary_domain=HealthDomain.GENERAL,
                confidence=0.3,
                keywords_found=[]
            )
        
        # Create domain tags sorted by number of matches
        tags = []
        for domain, keywords in domain_scores.items():
            confidence = min(len(keywords) * 0.25 + 0.4, 1.0)
            tags.append(DomainTag(
                domain=domain,
                confidence=confidence,
                matched_keywords=keywords
            ))
        
        tags.sort(key=lambda t: t.confidence, reverse=True)
        
        return DomainResult(
            primary_domain=tags[0].domain,
            confidence=tags[0].confidence,
            all_domains=tags,
            keywords_found=all_keywords
        )
    
    def tag_batch(self, texts: List[str]) -> List[DomainResult]:
        """Tag multiple texts."""
        return [self.tag(text) for text in texts]
    
    def extract_domain_keywords(self, text: str, domain: HealthDomain) -> List[str]:
        """Extract keywords for a specific domain from text."""
        if domain not in self._patterns:
            return []
        
        keywords = []
        for pattern in self._patterns[domain]:
            matches = pattern.findall(text)
            keywords.extend(matches)
        
        return list(set(keywords))
    
    def get_domain_description(self, domain: HealthDomain) -> str:
        """Get human-readable description of a domain."""
        descriptions = {
            HealthDomain.DENGUE: "Dengue fever and related mosquito-borne diseases",
            HealthDomain.COVID: "COVID-19 and coronavirus-related information",
            HealthDomain.VACCINATION: "Vaccines and immunization programs",
            HealthDomain.MENTAL_HEALTH: "Mental health and psychiatric services",
            HealthDomain.MATERNAL_HEALTH: "Maternal and reproductive health",
            HealthDomain.CHILD_HEALTH: "Pediatric and child health services",
            HealthDomain.OPD: "Outpatient department and general consultations",
            HealthDomain.EMERGENCY: "Emergency and trauma services",
            HealthDomain.PHARMACY: "Pharmacy and medication information",
            HealthDomain.LABORATORY: "Laboratory and diagnostic services",
            HealthDomain.DENTAL: "Dental and oral health services",
            HealthDomain.EYE: "Eye care and ophthalmology services",
            HealthDomain.GENERAL: "General health information",
        }
        return descriptions.get(domain, "Health services")


# Convenience function
def tag_domain(text: str) -> DomainResult:
    """Convenience function for domain tagging."""
    tagger = HealthDomainTagger()
    return tagger.tag(text)
