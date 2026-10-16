from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, StringConstraints

from .rules import Result, check, load_ruleset, search_items

DATA_DIR = Path(__file__).parent.parent / "data"
RULESET = load_ruleset(DATA_DIR)

app = FastAPI(title="迷你出口合规查询台")


class CheckRequest(BaseModel):
    eccn: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20)]
    country: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=2, max_length=2)]
    end_user: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


def run_check(req: CheckRequest) -> Result:
    try:
        return check(RULESET, req.eccn, req.country, req.end_user)
    except ValueError as e:
        raise HTTPException(422, detail=str(e)) from e


@app.get("/api/items")
def items(q: str = "") -> list[dict]:
    return search_items(RULESET, q)


@app.get("/api/countries")
def countries() -> list[dict]:
    return [
        {"code": code, "name_zh": c["name_zh"], "embargoed": c["embargo"] is not None}
        for code, c in sorted(RULESET.countries.items())
    ]


@app.post("/api/check", response_model=Result)
def check_endpoint(req: CheckRequest) -> Result:
    return run_check(req)
