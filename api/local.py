"""Single-origin local assembly: Django login, sprint API and compiled Vue assets."""
from pathlib import Path
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
from starlette.staticfiles import StaticFiles
from api.main import create_app

app = create_app()
assets = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "assets"
if assets.is_dir():
    app.mount("/sprint/assets", StaticFiles(directory=assets), name="sprint-assets")
app.mount("/", ASGIStaticFilesHandler(get_asgi_application()))
