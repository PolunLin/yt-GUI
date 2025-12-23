from fastapi import APIRouter, Depends

from apps.api.app.api.deps import require_api_key
from apps.api.app.api.routes.health import router as health_router
from apps.api.app.api.routes.videos import router as videos_router
from apps.api.app.api.routes.downloads import router as downloads_router
from apps.api.app.api.routes.me import router as me_router

api_router = APIRouter()

# health 不上鎖
api_router.include_router(health_router, prefix="/health", tags=["health"])

# 其餘都上鎖（這樣 me.py 不用自己寫 Depends）
api_router.include_router(
    videos_router, prefix="/videos", tags=["videos"], dependencies=[Depends(require_api_key)]
)
api_router.include_router(
    downloads_router, prefix="/downloads", tags=["downloads"], dependencies=[Depends(require_api_key)]
)
api_router.include_router(
    me_router, prefix="/me", tags=["auth"], dependencies=[Depends(require_api_key)]
)