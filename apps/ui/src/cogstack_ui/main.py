from __future__ import annotations

from fastapi import FastAPI

from cogstack_ui.routes.dashboard import router as dashboard_router
from cogstack_ui.routes.outreach import router as outreach_router
from cogstack_ui.routes.prospects import router as prospects_router

app = FastAPI(title="CogStack Leadgen")
app.include_router(dashboard_router)
app.include_router(prospects_router)
app.include_router(outreach_router)
