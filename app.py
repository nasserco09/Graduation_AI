from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.routing import Mount, Route

from backend.main import app as backend_app

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

if not (FRONTEND_DIR / "index.html").is_file():
    raise RuntimeError(f"Frontend not found: {FRONTEND_DIR}")

STYLE_DIR = FRONTEND_DIR / "styles"
if not STYLE_DIR.is_dir():
    STYLE_DIR = FRONTEND_DIR / "style"

app = backend_app

# Remove only old frontend routes if this module reloads. Keep every /api route intact.
frontend_names = {
    "frontend_home", "frontend_index", "frontend_about",
    "frontend_style", "frontend_styles", "frontend_js", "frontend_assets"
}
clean_routes = []
for route in app.router.routes:
    if isinstance(route, APIRoute) and route.path == "/" and "GET" in (route.methods or set()):
        continue
    if getattr(route, "name", "") in frontend_names:
        continue
    clean_routes.append(route)

async def frontend_home(request):
    return FileResponse(FRONTEND_DIR / "index.html")

async def frontend_index(request):
    return FileResponse(FRONTEND_DIR / "index.html")

async def frontend_about(request):
    return FileResponse(FRONTEND_DIR / "about.html")

frontend_routes = [
    # Serve both spellings so style/styles naming can never break the page.
    Mount("/style", app=StaticFiles(directory=str(STYLE_DIR)), name="frontend_style"),
    Mount("/styles", app=StaticFiles(directory=str(STYLE_DIR)), name="frontend_styles"),
    Mount("/js", app=StaticFiles(directory=str(FRONTEND_DIR / "js")), name="frontend_js"),
    Mount("/assets", app=StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="frontend_assets"),
    Route("/", endpoint=frontend_home, methods=["GET"], name="frontend_home"),
    Route("/index.html", endpoint=frontend_index, methods=["GET"], name="frontend_index"),
    Route("/about.html", endpoint=frontend_about, methods=["GET"], name="frontend_about"),
]

app.router.routes = frontend_routes + clean_routes

print("=" * 60)
print("AI + FRONTEND APPLICATION")
print(f"Frontend: {FRONTEND_DIR}")
print("Home:     http://127.0.0.1:8000/")
print("API Docs: http://127.0.0.1:8000/docs")
print("=" * 60)
