import dataclasses
from pathlib import Path

import pytest

from app.rules import (
    CheckInput,
    Ruleset,
    check,
    load_ruleset,
    normalize_name,
    search_items,
)

RS = Ruleset(
    items={
        "5A002": {"eccn": "5A002", "title": "Information security systems", "title_zh": "信息安全系统",
                  "keywords": ["加密"], "controls": ["NS1", "AT1"],
                  "special_controls": [{"reason": "EI", "citation": "15 CFR 742.15"}]},
        "5A992": {"eccn": "5A992", "title": "Mass market information security items", "title_zh": "大众市场信息安全物项",
                  "keywords": ["大众市场"], "controls": ["AT1"], "special_controls": []},
        "3A001": {"eccn": "3A001", "title": "Electronic items", "title_zh": "电子元器件",
                  "keywords": ["电子"], "controls": ["NS2"], "special_controls": []},
    },
    countries={
        "CN": {"name_zh": "中国", "x_columns": ["NS1", "NS2"], "embargo": None},
        "JP": {"name_zh": "日本", "x_columns": [], "embargo": None},
        "KP": {"name_zh": "朝鲜", "x_columns": ["NS1", "NS2", "AT1"], "embargo": "15 CFR 746.4"},
        "CU": {"name_zh": "古巴", "x_columns": [], "embargo": "15 CFR 746.2"},
    },
    entities=[{"name": "Huawei Technologies Co., Ltd.", "aliases": ["Huawei"], "country": "CN",
               "license_requirement": "For all items subject to the EAR", "review_policy": "Presumption of denial",
               "fr_citation": "84 FR 22961"}],
    version="test", sources=[], digest="deadbeef",
)


def rules(r):
    return {f.rule for f in r.findings}


def by_rule(r, rule):
    return [f for f in r.findings if f.rule == rule]


@pytest.mark.parametrize("eccn,country,end_user,decision,expected", [
    ("5A002", "KP", None, "LICENSE_REQUIRED", {"embargo", "country_chart", "special_control"}),
    ("3A001", "CN", None, "LICENSE_REQUIRED", {"country_chart"}),
    ("5A992", "CN", None, "NLR", {"country_chart"}),
    ("EAR99", "JP", None, "NLR", {"country_chart"}),
    ("5A002", "JP", None, "NEEDS_REVIEW", {"country_chart", "special_control"}),
    ("5A992", "JP", "HUAWEI TECHNOLOGIES CO LTD", "LICENSE_REQUIRED", {"country_chart", "entity_list"}),
    ("5A992", "JP", "Huawei Technologis", "NEEDS_REVIEW", {"country_chart", "entity_list"}),
    ("5A992", "JP", "Huawei Device", "NEEDS_REVIEW", {"country_chart", "entity_list"}),
    ("5A992", "JP", "Sony Group", "NLR", {"country_chart", "entity_list"}),
    ("5A002", "CN", "Huawei", "LICENSE_REQUIRED", {"country_chart", "special_control", "entity_list"}),
])
def test_check_table(eccn, country, end_user, decision, expected):
    r = check(RS, eccn, country, end_user)
    assert r.decision == decision
    assert rules(r) == expected


def test_country_chart_hit_per_column():
    r = check(RS, "5A002", "CN", None)
    (f,) = by_rule(r, "country_chart")
    assert r.decision == "LICENSE_REQUIRED"
    assert "NS1" in f.message
    assert "738 Supp. 1" in f.citation and "5A002" in f.citation


def test_country_chart_miss_explains():
    r = check(RS, "5A992", "CN", None)
    (f,) = by_rule(r, "country_chart")
    assert f.decision == "NLR" and "AT1" in f.message


def test_ear99_citation():
    assert by_rule(check(RS, "EAR99", "JP", None), "country_chart")[0].citation == "15 CFR 734.3(c)"


def test_embargo_citation():
    assert by_rule(check(RS, "5A002", "KP", None), "embargo")[0].citation == "15 CFR 746.4"


def test_embargo_without_chart_row_has_no_chart_miss():
    r = check(RS, "5A992", "CU", None)
    assert r.decision == "LICENSE_REQUIRED"
    assert rules(r) == {"embargo"}


def test_item_without_chart_controls():
    rs = dataclasses.replace(RS, items={**RS.items, "5A980": {
        "eccn": "5A980", "title": "x", "title_zh": "x", "keywords": [], "controls": [],
        "special_controls": [{"reason": "SL", "citation": "15 CFR 742.13"}]}})
    r = check(rs, "5A980", "JP", None)
    (f,) = by_rule(r, "country_chart")
    assert f.decision == "NLR" and f.message == "5A980 无国家表管制栏"
    assert f.citation == "15 CFR 738 Supp. 1；15 CFR 774 Supp. 1（5A980）"
    assert r.decision == "NEEDS_REVIEW"


def test_entity_exact_citation():
    (f,) = by_rule(check(RS, "5A992", "JP", "Huawei"), "entity_list")
    assert "744.11" in f.citation and "84 FR 22961" in f.citation


def test_fuzzy_message_has_match_and_score():
    (f,) = by_rule(check(RS, "5A992", "JP", "Huawei Technologis"), "entity_list")
    assert "Huawei Technologies Co., Ltd." in f.message and "0.9" in f.message


def test_input_is_normalized():
    r = check(RS, "5a002 ", " jp", "  ")
    assert r.input == CheckInput("5A002", "JP", None)
    assert "entity_list" not in rules(r)


def test_chinese_end_user_warns_english_only():
    (f,) = by_rule(check(RS, "5A992", "JP", "华为"), "entity_list")
    assert f.decision == "NEEDS_REVIEW" and "英文" in f.message


def test_end_user_without_valid_chars_needs_review():
    (f,) = by_rule(check(RS, "5A992", "JP", "Co., Ltd."), "entity_list")
    assert f.decision == "NEEDS_REVIEW" and "英文" in f.message


def test_unknown_eccn_raises():
    with pytest.raises(ValueError, match="未知 ECCN：9Z999"):
        check(RS, "9Z999", "JP", None)


def test_unknown_country_raises():
    with pytest.raises(ValueError, match="未知国家：ZZ"):
        check(RS, "5A002", "ZZ", None)


def test_result_carries_ruleset():
    r = check(RS, "5A002", "JP", None)
    assert (r.ruleset_version, r.ruleset_digest) == ("test", "deadbeef")


def test_normalize_name():
    assert normalize_name("HUAWEI TECHNOLOGIES CO., LTD.") == "huaweitechnologies"
    assert normalize_name("Huawei Technologies Co., Ltd.") == "huaweitechnologies"
    assert normalize_name("华为技术有限公司") == "华为技术有限公司"
    assert normalize_name("Co., Ltd.") == ""


def test_search_eccn_prefix_first():
    assert search_items(RS, "5a0")[0]["eccn"] == "5A002"


def test_search_keyword():
    assert [i["eccn"] for i in search_items(RS, "加密")] == ["5A002"]


def test_search_blank_and_special_chars():
    assert [i["eccn"] for i in search_items(RS, "  ")] == ["3A001", "5A002", "5A992"]
    assert search_items(RS, "%(") == []


RS_INSPUR = dataclasses.replace(RS, entities=[{
    "name": "Inspur Group Co., Ltd.", "aliases": [], "country": "CN",
    "license_requirement": "For all items subject to the EAR", "review_policy": "Presumption of denial",
    "fr_citation": "88 FR 13675"}])


def test_partial_name_needs_review():
    (f,) = by_rule(check(RS_INSPUR, "5A992", "JP", "Inspur"), "entity_list")
    assert f.decision == "NEEDS_REVIEW"
    assert "部分重合" in f.message and "Inspur Group Co., Ltd." in f.message
    assert "88 FR 13675" in f.citation


def test_partial_name_too_short_is_ignored():
    (f,) = by_rule(check(RS_INSPUR, "5A992", "JP", "Ins"), "entity_list")
    assert f.decision == "NLR"


def test_real_data_short_huawei_is_flagged():
    rs = load_ruleset(Path(__file__).resolve().parents[1] / "data")
    (f,) = by_rule(check(rs, "5A992", "JP", "Huawei"), "entity_list")
    assert f.decision == "NEEDS_REVIEW"


def _real_entity(end_user):
    rs = load_ruleset(Path(__file__).resolve().parents[1] / "data")
    return by_rule(check(rs, "5A991", "JP", end_user), "entity_list")[0]


def test_real_data_mixed_chinese_english_is_flagged():
    assert _real_entity("华为 Huawei").decision == "NEEDS_REVIEW"


def test_real_data_chinese_only_is_flagged():
    assert _real_entity("华为技术有限公司").decision == "NEEDS_REVIEW"
