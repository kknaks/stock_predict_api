"""
모델 리포트 API

- GET /reports              → 버전 목록
- GET /reports/{version}    → report.md 내용 (이미지 경로 치환)
- GET /reports/{version}/images/{filename} → PNG 파일
"""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import DbSession
from app.config.settings import settings
from app.database.database.model_registry import ModelRegistry
from app.schemas.report import ReportDetailResponse, ReportListItem, ReportListResponse

router = APIRouter()

MODELS_BASE_DIR = Path(settings.models_base_dir)
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg"}


@router.get("", response_model=ReportListResponse, status_code=status.HTTP_200_OK)
async def get_report_list(db: DbSession):
    """모델 버전 목록 조회 (최신순)"""
    result = await db.execute(
        select(ModelRegistry).order_by(ModelRegistry.id.desc())
    )
    registries = result.scalars().all()
    return ReportListResponse(
        data=[ReportListItem.model_validate(r) for r in registries]
    )


@router.get("/{version}", response_model=ReportDetailResponse, status_code=status.HTTP_200_OK)
async def get_report_detail(version: str, db: DbSession):
    """report.md 내용 반환 (이미지 경로를 API URL로 치환)"""
    result = await db.execute(
        select(ModelRegistry).where(ModelRegistry.version == version)
    )
    registry = result.scalar_one_or_none()
    if not registry:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    report_path = MODELS_BASE_DIR / version / "report.md"
    if not report_path.is_file():
        raise HTTPException(status_code=404, detail="report.md not found")

    content = report_path.read_text(encoding="utf-8")

    # 이미지 경로 치환: ![alt](./foo.png) → ![alt](/api/v1/reports/{version}/images/foo.png)
    content = re.sub(
        r"!\[([^\]]*)\]\(\./([^)]+)\)",
        rf"![\1](/api/v1/reports/{version}/images/\2)",
        content,
    )

    return ReportDetailResponse(
        version=registry.version,
        status=registry.status.value if hasattr(registry.status, "value") else str(registry.status),
        content=content,
    )


@router.get(
    "/{version}/images/{filename}",
    status_code=status.HTTP_200_OK,
    responses={200: {"content": {"image/png": {}}}},
)
async def get_report_image(version: str, filename: str):
    """리포트 이미지 파일 반환"""
    file_path = (MODELS_BASE_DIR / version / filename).resolve()

    # path traversal 방지
    if not str(file_path).startswith(str(MODELS_BASE_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")

    if file_path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(file_path)
