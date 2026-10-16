from fastapi.testclient import TestClient

from app.main import RULESET, app

client = TestClient(app)


def test_items_eccn_first():
    r = client.get("/api/items", params={"q": "5A002"})
    assert r.status_code == 200
    assert r.json()[0]["eccn"] == "5A002"


def test_items_empty_returns_all():
    assert len(client.get("/api/items").json()) == len(RULESET.items)


def test_countries():
    by_code = {c["code"]: c for c in client.get("/api/countries").json()}
    assert by_code["KP"]["embargoed"] is True
    assert by_code["JP"]["embargoed"] is False
    assert all(c["name_zh"] for c in by_code.values())
    assert list(by_code) == sorted(by_code)


def test_check_ok():
    r = client.post("/api/check", json={"eccn": "5A002", "country": "CN"})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "LICENSE_REQUIRED"
    assert body["ruleset_digest"] == RULESET.digest


def test_check_lowercase_input():
    r = client.post("/api/check", json={"eccn": " 5a002", "country": "cn", "end_user": "  "})
    assert r.status_code == 200
    assert r.json()["input"] == {"eccn": "5A002", "country": "CN", "end_user": None}


def test_check_unknown_eccn():
    r = client.post("/api/check", json={"eccn": "9Z999", "country": "CN"})
    assert r.status_code == 422
    assert r.json()["detail"] == "未知 ECCN：9Z999"


def test_check_bad_country_length():
    r = client.post("/api/check", json={"eccn": "5A002", "country": "CHN"})
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


def test_check_end_user_too_long():
    r = client.post("/api/check", json={"eccn": "5A002", "country": "CN", "end_user": "a" * 201})
    assert r.status_code == 422
