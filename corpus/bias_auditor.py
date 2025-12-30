"""
Bias Auditing System

Tracks and reports corpus representation:
- Language distribution
- Region distribution
- Domain distribution
- Identifies underrepresented categories
- Generates bias reports
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
import logging

logger = logging.getLogger(__name__)


@dataclass
class BiasAlert:
    """An alert for representation bias."""
    category_type: str  # 'language', 'region', 'domain'
    category_value: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    current_count: int
    expected_minimum: int
    message: str


@dataclass
class BiasReport:
    """Complete bias audit report."""
    snapshot_date: date
    total_documents: int
    total_qa_pairs: int
    
    # Distributions
    language_distribution: Dict[str, int] = field(default_factory=dict)
    romanized_distribution: Dict[str, int] = field(default_factory=dict)
    region_distribution: Dict[str, int] = field(default_factory=dict)
    domain_distribution: Dict[str, int] = field(default_factory=dict)
    intent_distribution: Dict[str, int] = field(default_factory=dict)
    
    # Alerts
    alerts: List[BiasAlert] = field(default_factory=list)
    
    # Summary stats
    sinhala_percentage: float = 0.0
    tamil_percentage: float = 0.0
    english_percentage: float = 0.0
    romanized_percentage: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": str(uuid4()),
            "snapshot_date": self.snapshot_date.isoformat(),
            "total_documents": self.total_documents,
            "total_qa_pairs": self.total_qa_pairs,
            "language_distribution": self.language_distribution,
            "romanized_distribution": self.romanized_distribution,
            "region_distribution": self.region_distribution,
            "domain_distribution": self.domain_distribution,
            "intent_distribution": self.intent_distribution,
            "bias_alerts": [
                {
                    "type": a.category_type,
                    "value": a.category_value,
                    "severity": a.severity,
                    "count": a.current_count,
                    "message": a.message
                }
                for a in self.alerts
            ]
        }


class BiasAuditor:
    """
    Audits corpus for representation bias.
    
    Checks for underrepresentation in:
    - Languages (should have Sinhala, Tamil, English balance)
    - Regions (urban vs rural)
    - Domains (not just dengue, but mental health, maternal, etc.)
    """
    
    # Minimum representation thresholds (percentage)
    MIN_THRESHOLDS = {
        "language": {
            "sinhala": 20,  # At least 20% Sinhala content
            "tamil": 15,    # At least 15% Tamil content
            "english": 10,  # At least 10% English content
        },
        "romanized": {
            "singlish": 5,  # At least 5% Singlish
            "tamilish": 3,  # At least 3% Tamilish
        },
        "domain": {
            "mental_health": 5,  # Mental health often underrepresented
            "maternal_health": 5,
            "child_health": 5,
        }
    }
    
    def __init__(self, repo: Optional[Any] = None):
        """
        Initialize the auditor.
        
        Args:
            repo: SupabaseRepo instance for fetching data
        """
        self.repo = repo
    
    def calculate_distribution(self, repo: Optional[Any] = None) -> BiasReport:
        """
        Calculate current corpus distribution.
        
        Args:
            repo: Optional repo override
            
        Returns:
            BiasReport with distributions and alerts
        """
        repo = repo or self.repo
        
        if not repo:
            logger.warning("No repo provided, returning empty report")
            return BiasReport(
                snapshot_date=date.today(),
                total_documents=0,
                total_qa_pairs=0
            )
        
        # Initialize report
        report = BiasReport(
            snapshot_date=date.today(),
            total_documents=0,
            total_qa_pairs=0
        )
        
        try:
            # Fetch document statistics
            resp = repo.supabase.table("raw_ingest").select(
                "detected_language,is_romanized,romanized_type,domain,region"
            ).limit(10000).execute()
            
            rows = getattr(resp, "data", None) or []
            report.total_documents = len(rows)
            
            # Calculate distributions
            for row in rows:
                # Language
                lang = row.get("detected_language") or "unknown"
                report.language_distribution[lang] = report.language_distribution.get(lang, 0) + 1
                
                # Romanized type
                if row.get("is_romanized"):
                    rom_type = row.get("romanized_type") or "mixed"
                    report.romanized_distribution[rom_type] = report.romanized_distribution.get(rom_type, 0) + 1
                
                # Domain
                domain = row.get("domain") or "general"
                report.domain_distribution[domain] = report.domain_distribution.get(domain, 0) + 1
                
                # Region
                region = row.get("region") or "unknown"
                report.region_distribution[region] = report.region_distribution.get(region, 0) + 1
            
            # Fetch Q&A statistics
            qa_resp = repo.supabase.table("qa_pairs").select("question_language,domain", count="exact").execute()
            qa_count = getattr(qa_resp, "count", None)
            if qa_count is not None:
                report.total_qa_pairs = qa_count
            else:
                report.total_qa_pairs = len(getattr(qa_resp, "data", None) or [])
            
            # Calculate percentages
            if report.total_documents > 0:
                report.sinhala_percentage = (report.language_distribution.get("sinhala", 0) / report.total_documents) * 100
                report.tamil_percentage = (report.language_distribution.get("tamil", 0) / report.total_documents) * 100
                report.english_percentage = (report.language_distribution.get("english", 0) / report.total_documents) * 100
                
                romanized_total = sum(report.romanized_distribution.values())
                report.romanized_percentage = (romanized_total / report.total_documents) * 100
            
            # Generate alerts
            report.alerts = self._generate_alerts(report)
            
        except Exception as e:
            logger.error(f"Error calculating distribution: {e}")
        
        return report
    
    def _generate_alerts(self, report: BiasReport) -> List[BiasAlert]:
        """Generate alerts for underrepresented categories."""
        alerts = []
        
        if report.total_documents == 0:
            return alerts
        
        # Check language thresholds
        for lang, min_pct in self.MIN_THRESHOLDS["language"].items():
            count = report.language_distribution.get(lang, 0)
            current_pct = (count / report.total_documents) * 100
            
            if current_pct < min_pct:
                severity = "critical" if current_pct < min_pct / 2 else "high" if current_pct < min_pct else "medium"
                alerts.append(BiasAlert(
                    category_type="language",
                    category_value=lang,
                    severity=severity,
                    current_count=count,
                    expected_minimum=int(report.total_documents * min_pct / 100),
                    message=f"{lang.title()} content is underrepresented: {current_pct:.1f}% (minimum: {min_pct}%)"
                ))
        
        # Check domain thresholds
        for domain, min_pct in self.MIN_THRESHOLDS["domain"].items():
            count = report.domain_distribution.get(domain, 0)
            current_pct = (count / report.total_documents) * 100
            
            if current_pct < min_pct:
                severity = "medium" if current_pct > 0 else "high"
                alerts.append(BiasAlert(
                    category_type="domain",
                    category_value=domain,
                    severity=severity,
                    current_count=count,
                    expected_minimum=int(report.total_documents * min_pct / 100),
                    message=f"{domain.replace('_', ' ').title()} content needs more coverage: {current_pct:.1f}%"
                ))
        
        return alerts
    
    def identify_gaps(self, report: BiasReport) -> List[Dict[str, Any]]:
        """
        Identify specific gaps that need to be filled.
        
        Returns:
            List of gap dictionaries with suggestions
        """
        gaps = []
        
        for alert in report.alerts:
            if alert.severity in ("high", "critical"):
                gap = {
                    "type": alert.category_type,
                    "category": alert.category_value,
                    "current": alert.current_count,
                    "needed": alert.expected_minimum - alert.current_count,
                    "suggestions": self._suggest_sources(alert.category_type, alert.category_value)
                }
                gaps.append(gap)
        
        return gaps
    
    def _suggest_sources(self, category_type: str, category_value: str) -> List[str]:
        """Suggest sources to fill representation gaps."""
        suggestions = {
            ("language", "tamil"): [
                "http://www.health.gov.lk/ta/",
                "Jaffna Teaching Hospital website",
                "Tamil language health hotline transcripts"
            ],
            ("language", "sinhala"): [
                "http://www.health.gov.lk/si/",
                "Sinhala health brochures",
                "MOH area office documents"
            ],
            ("domain", "mental_health"): [
                "National Institute of Mental Health website",
                "Suicide prevention hotline transcripts",
                "Psychiatric ward FAQs"
            ],
            ("domain", "maternal_health"): [
                "De Soysa Hospital for Women website",
                "Antenatal clinic schedules",
                "MOH maternal health programs"
            ]
        }
        
        return suggestions.get((category_type, category_value), [
            f"Search for more {category_value} content",
            f"Add {category_value} sources to crawl queue"
        ])
    
    def generate_markdown_report(self, report: BiasReport) -> str:
        """Generate a markdown-formatted bias report."""
        lines = [
            f"# Corpus Bias Audit Report",
            f"**Date:** {report.snapshot_date.isoformat()}",
            "",
            f"## Summary",
            f"- **Total Documents:** {report.total_documents:,}",
            f"- **Total Q&A Pairs:** {report.total_qa_pairs:,}",
            "",
            f"## Language Distribution",
        ]
        
        for lang, count in sorted(report.language_distribution.items(), key=lambda x: -x[1]):
            pct = (count / report.total_documents * 100) if report.total_documents else 0
            lines.append(f"- {lang.title()}: {count:,} ({pct:.1f}%)")
        
        lines.extend([
            "",
            f"## Domain Distribution",
        ])
        
        for domain, count in sorted(report.domain_distribution.items(), key=lambda x: -x[1]):
            pct = (count / report.total_documents * 100) if report.total_documents else 0
            lines.append(f"- {domain.replace('_', ' ').title()}: {count:,} ({pct:.1f}%)")
        
        if report.alerts:
            lines.extend([
                "",
                f"## ⚠️ Bias Alerts ({len(report.alerts)})",
            ])
            
            for alert in report.alerts:
                emoji = "🔴" if alert.severity == "critical" else "🟠" if alert.severity == "high" else "🟡"
                lines.append(f"- {emoji} **{alert.severity.upper()}**: {alert.message}")
        
        return "\n".join(lines)
    
    def save_report(self, report: BiasReport, repo: Optional[Any] = None) -> str:
        """Save report to database."""
        repo = repo or self.repo
        if not repo:
            raise ValueError("No repo provided")
        
        return repo.insert_corpus_statistics(report.to_dict())


# Convenience function
def audit_corpus(repo: Any) -> BiasReport:
    """Convenience function to audit corpus."""
    auditor = BiasAuditor(repo)
    return auditor.calculate_distribution()
