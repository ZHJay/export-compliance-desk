import dataclasses
from datetime import datetime

from fastapi.testclient import TestClient

from app.main import RULESET, app
from app.report import TZ, render_html, render_pdf, report_id
from app.rules import check

client = TestClient(app)
NOW = datetime(2026, 10, 16, 9, 30, tzinfo=TZ)


def _result(end_user="Huawei"):
    return check(RULESET, "5A002", "CN", end_user)


def test_report_id_deterministic():
    a, b = report_id(_result()), report_id(_result())
    assert a == b and len(a) == 12
    int(a, 16)


def test_report_id_changes_with_input_and_digest():
    base = _result()
    assert report_id(base) != report_id(_result("Other Co"))
    assert report_id(base) != report_id(dataclasses.replace(base, ruleset_digest="deadbeef"))


def test_html_contents():
    r = _result()
    html = render_html(RULESET, r, NOW)
    item = RULESET.items["5A002"]
    for s in ["出口合规初筛报告", report_id(r), r.ruleset_version, r.ruleset_digest,
              "简化子集，仅供演示，不构成法律意见。", *[f.citation for f in r.findings],
              item["title_zh"], item["title"], "中国（CN）", RULESET.ecfr_issue_date, *RULESET.sources]:
        assert s in html


def test_html_ear99_has_no_ccl_title():
    html = render_html(RULESET, check(RULESET, "EAR99", "JP", None), NOW)
    assert "不在 CCL 上" in html and "日本（JP）" in html


def test_html_escapes_end_user():
    html = render_html(RULESET, _result("<b>x</b>"), NOW)
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>x</b>" not in html


def test_pdf_bytes():
    assert render_pdf(RULESET, _result(), NOW)[:4] == b"%PDF"


def test_report_endpoint():
    r = client.post("/api/report", json={"eccn": "5A002", "country": "CN"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="report-5A002-CN-' in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


def test_report_endpoint_unknown():
    assert client.post("/api/report", json={"eccn": "9Z999", "country": "CN"}).status_code == 422
