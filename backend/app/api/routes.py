from fastapi import APIRouter

from app.api.routes_health import router as health_router
from app.api.routes_runs import router as runs_router
from app.api.routes_artifacts import router as artifacts_router
from app.api.routes_workspaces import router as workspaces_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(runs_router, prefix="/runs", tags=["runs"])
router.include_router(artifacts_router, prefix="/artifacts", tags=["artifacts"])
router.include_router(workspaces_router, prefix="/workspaces", tags=["workspaces"])
