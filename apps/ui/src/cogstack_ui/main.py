from __future__ import annotations

import contextlib
import logging

from fastapi import FastAPI

# Uvicorn configures only its own loggers. Without this, cogstack_ui.*
# loggers propagate to a root logger with no handlers (silent).
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
)

from cogstack_ui.routes.dashboard import router as dashboard_router
from cogstack_ui.routes.outreach import router as outreach_router
from cogstack_ui.routes.prospects import router as prospects_router
from cogstack_ui.whatsapp.batches import mark_running_as_aborted_on_startup

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Flip any 'running' batches orphaned by a previous process crash/restart.
    try:
        flipped = mark_running_as_aborted_on_startup(
            reason="process restart — batch orphaned"
        )
        if flipped:
            logger.warning(
                "startup: flipped %d orphaned running batch%s to aborted",
                flipped, "es" if flipped != 1 else "",
            )
        else:
            logger.info("startup: no orphaned running batches found")
    except Exception:
        logger.exception(
            "startup: mark_running_as_aborted_on_startup failed — "
            "batches.json may be corrupt; continuing startup"
        )
    yield


app = FastAPI(title="CogStack Leadgen", lifespan=lifespan)
app.include_router(dashboard_router)
app.include_router(prospects_router)
app.include_router(outreach_router)
