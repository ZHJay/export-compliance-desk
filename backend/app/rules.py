"""Ruleset loading (stdlib only). Matching logic is added in later tasks."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CHART_COLUMNS = frozenset(
    ["CB1", "CB2", "CB3", "NP1", "NP2", "NS1", "NS2", "MT1", "RS1", "RS2", "CC1", "CC2", "CC3", "FC1", "AT1", "AT2"]
)
Decision = Literal["LICENSE_REQUIRED", "NEEDS_REVIEW", "NLR"]
_DIGEST_FILES = ("ccl.json", "country_chart.json", "entity_list.json")


@dataclass(frozen=True)
class Ruleset:
    items: dict[str, dict]
    countries: dict[str, dict]
    entities: list[dict]
    version: str
    sources: list[str]
    digest: str


def load_ruleset(data_dir: Path) -> Ruleset:
    raw = {f: (data_dir / f).read_bytes() for f in _DIGEST_FILES}
    meta = json.loads((data_dir / "meta.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(b"".join(raw[f] for f in _DIGEST_FILES)).hexdigest()[:8]
    return Ruleset(
        items={i["eccn"]: i for i in json.loads(raw["ccl.json"])["items"]},
        countries=json.loads(raw["country_chart.json"])["countries"],
        entities=json.loads(raw["entity_list.json"])["entities"],
        version=meta["version"],
        sources=meta["sources"],
        digest=digest,
    )
