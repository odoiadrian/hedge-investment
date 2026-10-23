from fastapi import FastAPI, Response, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, credential_fields_present
from .models import ClientProfile, PortfolioDashboard
from .pipeline import generate_dashboard, dataset_status, DataUnavailable
from .llm import AnalystUnavailable

app = FastAPI(
    title="HedgeHog API",
    description="Client-led portfolio analysis with the supplied quantitative model and event AI API.",
    version="1.0.0",
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict:
    return {
        "dataset": dataset_status(),
        "risk_model": "team_optimizer_v1",
        "event_api": "configured" if credential_fields_present() else "not_configured",
        "credential_fields_present": credential_fields_present(),
    }


@app.post("/api/recommendations", response_model=PortfolioDashboard)
def recommendations(profile: ClientProfile, response: Response) -> PortfolioDashboard:
    # No client persistence or body logging. AI receives preferences and evidence,
    # not the client's identifying reference.
    response.headers["Cache-Control"] = "no-store"
    try:
        return generate_dashboard(profile)
    except (AnalystUnavailable, DataUnavailable) as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Cache-Control": "no-store"}) from exc


# Optional single-server demo: build the frontend, then restart the backend.
# Development uses Vite's /api proxy and requires no permissive CORS policy.
frontend_dist = ROOT / "frontend" / "dist"
if (frontend_dist / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(frontend_dist / "index.html")
