"""FastAPI backend + single-page web UI (spec section 7: a backend is required
because SEC EDGAR has no CORS and must be called server-side).

Endpoints:
    GET  /                      -> the single-page app
    GET  /api/fields           -> attr -> friendly-label map (drives the grid)
    POST /api/ticker           -> analyze a public company by ticker (EDGAR)
    POST /api/parse            -> extract uploaded statement PDFs (unconfirmed)
    POST /api/analyze          -> compute from a user-confirmed company dict
    GET  /api/download/{token} -> download the generated live-formula .xlsx

Run:  python -m ivanalysis.webapp        (or: uvicorn ivanalysis.webapp.app:app)
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import markdown as md
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from ..edgar import EdgarClient, analyze_ticker
from ..excel import build_workbook
from ..metrics import run_ratios
from ..model import FIELD_LABEL
from ..report import generate_report, score_viability
from ..uploads import company_from_dict
from ..uploads.parse import parse_statements

app = FastAPI(title="Investment-Viability Analysis")

STATIC = Path(__file__).parent / "static"
WORKDIR = Path(tempfile.gettempdir()) / "ivanalysis_web"
WORKDIR.mkdir(exist_ok=True)
RESULTS: dict[str, dict] = {}  # token -> {xlsx: Path, name: str}

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _build_results(company) -> dict:
    company.normalize()
    if not company.periods:
        raise HTTPException(400, "No usable periods to analyze.")
    token = uuid.uuid4().hex[:12]
    slug = "".join(ch for ch in (company.ticker or company.name) if ch.isalnum()) or "company"
    xlsx = WORKDIR / f"{slug}_{token}.xlsx"
    build_workbook(company, xlsx)
    report_md = generate_report(company)
    report_path = WORKDIR / f"{slug}_{token}_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    RESULTS[token] = {"xlsx": xlsx, "report_md": report_path, "name": slug}

    report_html = md.markdown(report_md, extensions=["tables", "fenced_code", "sane_lists"])
    score = score_viability(company)
    latest = run_ratios(company, len(company.periods) - 1)
    metrics = [{
        "name": r.name, "category": r.category, "value": r.display(),
        "healthy": (r.healthy(r.value) if (r.healthy and r.value is not None) else None),
    } for r in latest]
    return {
        "token": token, "company_name": company.name,
        "verdict": score["verdict"], "points": score["points"], "max": score["max"],
        "ratio": round(score["ratio"] * 100), "drivers": score["drivers"],
        "periods": [p.label for p in company.periods],
        "metrics": metrics, "report_html": report_html,
        "xlsx_url": f"/api/download/{token}",
        "report_url": f"/api/download/{token}/report",
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/fields")
def fields() -> dict:
    return FIELD_LABEL


@app.post("/api/ticker")
def api_ticker(payload: dict) -> dict:
    ticker = (payload.get("ticker") or "").strip()
    if not ticker:
        raise HTTPException(400, "Ticker is required.")
    years = int(payload.get("years") or 4)
    try:
        company = analyze_ticker(ticker, years=years, client=EdgarClient())
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:  # network / EDGAR issues
        raise HTTPException(502, f"EDGAR request failed: {exc}")
    if not company.periods:
        raise HTTPException(404, f"No usable fiscal periods found for {ticker}.")
    _merge_assumptions(company, payload.get("assumptions"))
    return _build_results(company)


@app.post("/api/parse")
async def api_parse(files: list[UploadFile] = File(...),
                    name: str = Form("Uploaded Company")) -> dict:
    if not files:
        raise HTTPException(400, "Upload at least one PDF.")
    paths = []
    for f in files:
        dest = WORKDIR / f"upload_{uuid.uuid4().hex[:8]}_{Path(f.filename).name}"
        dest.write_bytes(await f.read())
        paths.append(dest)
    try:
        return parse_statements(paths, name=name)
    except NotImplementedError as exc:  # scanned PDF, no OCR available
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse upload: {exc}")


@app.post("/api/analyze")
def api_analyze(payload: dict) -> dict:
    # payload is the (user-confirmed) company dict, incl. optional assumptions.
    company = company_from_dict(payload)
    return _build_results(company)


@app.get("/api/download/{token}")
def download(token: str):
    item = RESULTS.get(token)
    if not item or not Path(item["xlsx"]).exists():
        raise HTTPException(404, "Result expired or not found. Re-run the analysis.")
    return FileResponse(item["xlsx"], filename=f"{item['name']}.xlsx", media_type=XLSX_MIME)


@app.get("/api/download/{token}/report")
def download_report(token: str):
    item = RESULTS.get(token)
    if not item or not Path(item["report_md"]).exists():
        raise HTTPException(404, "Result expired or not found. Re-run the analysis.")
    return FileResponse(item["report_md"], filename=f"{item['name']}_report.md",
                        media_type="text/markdown")


def _merge_assumptions(company, assumptions) -> None:
    if not isinstance(assumptions, dict):
        return
    for key, value in assumptions.items():
        if value in (None, "") or not hasattr(company.assumptions, key):
            continue
        try:
            setattr(company.assumptions, key, float(value))
        except (TypeError, ValueError):
            pass


def main() -> None:
    import os

    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
