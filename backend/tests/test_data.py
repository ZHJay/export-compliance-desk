import json
import re
import shutil
from pathlib import Path

from app.rules import CHART_COLUMNS, load_ruleset

DATA = Path(__file__).parent.parent / "data"
REQUIRED_ECCNS = {"3A001", "4A003", "5A002", "5A992"}
REQUIRED_COUNTRIES = {"CN", "JP", "DE", "RU", "IR", "KP", "CU"}
rs = load_ruleset(DATA)


def test_loads_and_digest():
    assert re.fullmatch(r"[0-9a-f]{8}", rs.digest)
    assert rs.version
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", rs.ecfr_issue_date)
    assert rs.sources


def test_required_coverage():
    assert REQUIRED_ECCNS <= rs.items.keys()
    assert REQUIRED_COUNTRIES <= rs.countries.keys()
    assert any("Huawei" in e["name"] for e in rs.entities)


def test_controls_are_chart_columns():
    for eccn, item in rs.items.items():
        assert set(item["controls"]) <= CHART_COLUMNS, eccn


def test_x_columns_are_chart_columns():
    for code, c in rs.countries.items():
        assert set(c["x_columns"]) <= CHART_COLUMNS, code


def test_special_controls_have_citation():
    for eccn, item in rs.items.items():
        for sc in item["special_controls"]:
            assert sc["reason"] and sc["citation"], eccn


def test_no_duplicate_eccns():
    items = json.loads((DATA / "ccl.json").read_text())["items"]
    eccns = [i["eccn"] for i in items]
    assert len(eccns) == len(set(eccns))


def test_embargoed_countries():
    for code in ("KP", "CU", "IR"):
        assert rs.countries[code]["embargo"]
    assert rs.countries["JP"]["embargo"] is None


def test_digest_changes_with_data(tmp_path):
    shutil.copytree(DATA, tmp_path / "d")
    p = tmp_path / "d" / "ccl.json"
    p.write_bytes(p.read_bytes() + b" ")
    assert load_ruleset(tmp_path / "d").digest != rs.digest
