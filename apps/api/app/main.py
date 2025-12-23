from fastapi import FastAPI
from apps.api.app.api.router import api_router
from apps.api.app.db.models import video, download_job
app = FastAPI(title="YT GUI API")
app.include_router(api_router)


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

WEB_DIST = Path("/app/apps/web/dist")

if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")

    @app.get("/")
    def root():
        return FileResponse(WEB_DIST / "index.html")