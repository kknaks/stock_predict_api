"""
API 공통 의존성 (Dependencies)
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_db

# DB 세션 의존성 타입
DbSession = Annotated[AsyncSession, Depends(get_db)]
