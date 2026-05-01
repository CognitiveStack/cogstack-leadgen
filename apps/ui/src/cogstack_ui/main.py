from __future__ import annotations

from fastapi import FastAPI

from cogstack_ui.routes.dashboard import router as dashboard_router

app = FastAPI(title="CogStack Leadgen")
app.include_router(dashboard_router)
