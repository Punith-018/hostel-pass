import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.auth import router as auth_router
from app.routes.passes import router as passes_router
from app.routes.board import router as board_router
from app.routes.notifications import router as notifications_router

app = FastAPI(title="Hostel Pass API")

# Mount API routers
app.include_router(auth_router, prefix="/api")
app.include_router(passes_router, prefix="/api")
app.include_router(board_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")

# Mount static files at / (Doc 02 Section 3 & Doc 04 Section 1)
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
