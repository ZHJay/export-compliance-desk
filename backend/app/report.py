"""Reproducible PDF report: Jinja2 -> WeasyPrint."""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from .rules import Result

TZ = ZoneInfo("Asia/Shanghai")
DISCLAIMER = "简化子集，仅供演示，不构成法律意见。"
DECISION_LABEL = {"LICENSE_REQUIRED": "需许可证", "NEEDS_REVIEW": "需人工复核", "NLR": "无需许可证"}
RULE_LABEL = {"embargo": "禁运", "country_chart": "国家表", "special_control": "特殊管制", "entity_list": "实体清单"}

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape(["html"])
)


def report_id(result: Result) -> str:
    payload = json.dumps(asdict(result.input), sort_keys=True, ensure_ascii=False) + result.ruleset_digest
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def render_html(result: Result, generated_at: datetime) -> str:
    return _env.get_template("report.html").render(
        r=result,
        report_id=report_id(result),
        generated_at=generated_at.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S"),
        decision_label=DECISION_LABEL[result.decision],
        rule_label=RULE_LABEL,
        decision_labels=DECISION_LABEL,
        disclaimer=DISCLAIMER,
    )


def render_pdf(result: Result, generated_at: datetime) -> bytes:
    return HTML(string=render_html(result, generated_at)).write_pdf()
