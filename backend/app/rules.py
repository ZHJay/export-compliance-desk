"""Ruleset loading and decision logic (stdlib only)."""

import difflib
import hashlib
import json
import re
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
    # engine source is hashed too, so any change to the decision logic changes the report ID
    digest = hashlib.sha256(b"".join(raw[f] for f in _DIGEST_FILES) + Path(__file__).read_bytes()).hexdigest()[:8]
    return Ruleset(
        items={i["eccn"]: i for i in json.loads(raw["ccl.json"])["items"]},
        countries=json.loads(raw["country_chart.json"])["countries"],
        entities=json.loads(raw["entity_list.json"])["entities"],
        version=meta["version"],
        sources=meta["sources"],
        digest=digest,
    )


_SUFFIXES = frozenset(["co", "company", "ltd", "limited", "inc", "incorporated", "corp", "corporation", "llc", "plc", "gmbh"])
_SEVERITY = {"NLR": 0, "NEEDS_REVIEW": 1, "LICENSE_REQUIRED": 2}
_CHART_CITE = "15 CFR 738 Supp. 1"
_ENTITY_CITE = "15 CFR 744 Supp. 4"


@dataclass(frozen=True)
class Finding:
    rule: Literal["embargo", "country_chart", "special_control", "entity_list"]
    decision: Decision
    message: str
    citation: str


@dataclass(frozen=True)
class CheckInput:
    eccn: str
    country: str
    end_user: str | None


@dataclass(frozen=True)
class Result:
    decision: Decision
    findings: list[Finding]
    ruleset_version: str
    ruleset_digest: str
    input: CheckInput


def _words(name: str) -> list[str]:
    return [w for w in re.split(r"[^\w]+", name.casefold()) if w and w not in _SUFFIXES]


def normalize_name(name: str) -> str:
    return "".join(_words(name))


def _latin(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", normalize_name(s))


def _latin_words(s: str) -> set[str]:
    return {w for w in (re.sub(r"[^0-9a-z]", "", w) for w in _words(s)) if w}


def search_items(rs: Ruleset, q: str) -> list[dict]:
    q = q.strip().casefold()
    scored = []
    for eccn, item in rs.items.items():
        if not q:
            score = 0
        elif eccn.casefold().startswith(q):
            score = 3
        elif q in item["title"].casefold() or q in item["title_zh"].casefold():
            score = 2
        elif any(q in k.casefold() for k in item["keywords"]):
            score = 1
        else:
            continue
        scored.append((-score, eccn, item))
    return [item for _, _, item in sorted(scored, key=lambda t: t[:2])]


def _chart_findings(item: dict, eccn: str, country: dict) -> list[Finding]:
    if eccn == "EAR99":
        return [Finding("country_chart", "NLR", "EAR99 物项不受国家表管制", "15 CFR 734.3(c)")]
    miss_cite = f"{_CHART_CITE}；15 CFR 774 Supp. 1（{eccn}）"
    if not item["controls"]:
        return [Finding("country_chart", "NLR", f"{eccn} 无国家表管制栏", miss_cite)]
    name = country["name_zh"]
    hits = [c for c in item["controls"] if c in country["x_columns"]]
    if hits:
        return [
            Finding("country_chart", "LICENSE_REQUIRED", f"{eccn} 的管制栏 {c} 在{name}打 X",
                    f"{_CHART_CITE}（{c}）；15 CFR 774 Supp. 1（{eccn}）")
            for c in hits
        ]
    if country["embargo"]:  # embargo line already decides the outcome for every embargoed destination; CU/IR/KP/SY chart rows are additionally empty (Part 746)
        return []
    cols = "、".join(item["controls"])
    return [Finding("country_chart", "NLR", f"{eccn} 的管制栏 {cols} 在{name}均未打 X", miss_cite)]


def _entity_finding(rs: Ruleset, end_user: str) -> Finding:
    key = _latin(end_user)
    if not key:
        return Finding("entity_list", "NEEDS_REVIEW",
                       "最终用户名称不含可比对的英文字母或数字（实体清单仅有英文名称），无法筛查，需人工复核", _ENTITY_CITE)
    key_words = _latin_words(end_user)
    best, best_score, partial = None, 0.0, None
    for e in rs.entities:
        for n in [e["name"], *e["aliases"]]:
            cand = _latin(n)
            short, long = sorted((key, cand), key=len)
            # substring needs >= 4 chars; shorter names (DJI, ZTE) count only as a whole word of the other name
            overlap = (len(short) >= 4 and short in long) or cand in key_words or key in _latin_words(n)
            if partial is None and overlap:
                partial = e
            score = 1.0 if cand == key else difflib.SequenceMatcher(None, key, cand).ratio()
            if score > best_score:
                best, best_score = e, score
    # ponytail: 0.85 为经验阈值，基于字符序列；另有互相包含兜底（≥4 字符按子串，如 Huawei；更短按整词，如 DJI）；误报/漏报需要时换 rapidfuzz token_set_ratio + 人工标注集调参
    if best and best_score >= 0.85:
        cite = f"15 CFR 744.11；15 CFR 744 Supp. 4（{best['fr_citation']}）"
        if best_score == 1.0:
            msg = (f"最终用户与实体清单条目「{best['name']}」（{best['country']}）一致；"
                   f"许可要求：{best['license_requirement']}；审查政策：{best['review_policy']}")
            return Finding("entity_list", "LICENSE_REQUIRED", msg, cite)
        msg = f"最终用户与实体清单条目「{best['name']}」相似度 {best_score:.2f}，疑似命中，需人工复核"
        return Finding("entity_list", "NEEDS_REVIEW", msg, cite)
    if partial:
        msg = f"最终用户与实体清单条目「{partial['name']}」部分重合，疑似命中，需人工复核"
        return Finding("entity_list", "NEEDS_REVIEW", msg,
                       f"15 CFR 744.11；15 CFR 744 Supp. 4（{partial['fr_citation']}）")
    return Finding("entity_list", "NLR", "未在实体清单子集中命中（仅比对英文名称及别名）", _ENTITY_CITE)


def check(rs: Ruleset, eccn: str, country: str, end_user: str | None) -> Result:
    eccn, country = eccn.strip().upper(), country.strip().upper()
    end_user = (end_user or "").strip() or None
    item = rs.items.get(eccn)
    if eccn != "EAR99" and item is None:
        raise ValueError(f"未知 ECCN：{eccn}")
    c = rs.countries.get(country)
    if c is None:
        raise ValueError(f"未知国家：{country}")

    findings: list[Finding] = []
    if c["embargo"]:
        findings.append(Finding("embargo", "LICENSE_REQUIRED", f"{c['name_zh']}受 15 CFR 746 禁运/制裁管制", c["embargo"]))
    findings += _chart_findings(item, eccn, c)
    for sc in (item or {}).get("special_controls", []):
        findings.append(Finding("special_control", "NEEDS_REVIEW",
                                f"{sc['reason']} 管制（{sc['citation']}）按条款所列条件适用、不按国家表栏位，本子集未编码，需人工复核", sc["citation"]))
    if end_user:
        findings.append(_entity_finding(rs, end_user))
    decision = max((f.decision for f in findings), key=_SEVERITY.__getitem__, default="NLR")
    return Result(decision, findings, rs.version, rs.digest, CheckInput(eccn, country, end_user))
