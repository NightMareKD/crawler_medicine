"""Source registry for health-domain crawling.

Step 1 of the research component: make sources explicit and measurable.

- Stores canonical source definitions (agency, seed URLs, topic hints, reliability)
- Stores language mix targets for downstream balancing

The registry is intentionally file-backed (JSON) so unit tests can run without
Supabase. In production, you can mirror this into a `sources` table.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import json


@dataclass(frozen=True)
class Source:
    id: str
    agency: str
    seed_urls: List[str]
    reliability: float
    user_demand: float
    country: str
    region: str
    topics: List[str]
    notes: str = ""


class SourceRegistry:
    def __init__(self, sources: List[Source], language_targets: Dict[str, float]):
        self._sources = list(sources)
        self._by_id = {s.id: s for s in sources}
        self._language_targets = dict(language_targets)

    @staticmethod
    def _default_path() -> Path:
        return Path(__file__).with_name("sources.json")

    @classmethod
    def load_default(cls) -> "SourceRegistry":
        return cls.load_from_file(cls._default_path())

    @classmethod
    def load_from_file(cls, path: Path) -> "SourceRegistry":
        data = json.loads(path.read_text(encoding="utf-8"))

        language_targets = data.get("language_targets") or {}
        sources_raw = data.get("sources") or []

        sources: List[Source] = []
        for row in sources_raw:
            sources.append(
                Source(
                    id=str(row.get("id") or "").strip(),
                    agency=str(row.get("agency") or "").strip(),
                    seed_urls=list(row.get("seed_urls") or []),
                    reliability=float(row.get("reliability") or 0.0),
                    user_demand=float(row.get("user_demand") or 0.0),
                    country=str(row.get("country") or "").strip(),
                    region=str(row.get("region") or "").strip(),
                    topics=list(row.get("topics") or []),
                    notes=str(row.get("notes") or "").strip(),
                )
            )

        # Basic validation (keep minimal; avoid raising for future incremental edits)
        sources = [s for s in sources if s.id and s.agency]

        return cls(sources=sources, language_targets=language_targets)

    def list_sources(self) -> List[Source]:
        return list(self._sources)

    def get(self, source_id: str) -> Optional[Source]:
        return self._by_id.get(source_id)

    def language_targets(self) -> Dict[str, float]:
        return dict(self._language_targets)

    def seed_urls(self, source_id: str) -> List[str]:
        src = self.get(source_id)
        return list(src.seed_urls) if src else []

    def to_source_config(self, source_id: str, *, priority: str = "medium") -> Dict[str, Any]:
        """Create the `source_config` dict expected by URLManager/Crawler.

        This keeps the existing pipeline API stable while enabling Step 1 fields.
        """
        src = self.get(source_id)
        if not src:
            raise KeyError(f"Unknown source_id: {source_id}")
        return {
            "source_id": src.id,
            "agency": src.agency,
            "reliability": src.reliability,
            "user_demand": src.user_demand,
            "country": src.country,
            "region": src.region,
            "topics": src.topics,
            "priority": priority,
        }
