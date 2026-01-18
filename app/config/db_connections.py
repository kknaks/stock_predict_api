"""
PostgreSQL 비동기 데이터베이스 연결

asyncpg + SQLAlchemy async 사용
"""

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import settings

logger = logging.getLogger(__name__)

# 비동기 엔진 (싱글톤)
_engine = None
_async_session_factory = None


def get_engine():
    """비동기 엔진 반환 (싱글톤)"""
    global _engine
    
    if _engine is None:
        _engine = create_async_engine(
            settings.async_database_url,
            echo=settings.db_echo,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        logger.info(f"Database engine created: {settings.effective_db_host}:{settings.db_port}/{settings.db_name}")
    
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """세션 팩토리 반환"""
    global _async_session_factory
    
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency용 세션 제공
    
    Usage:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_factory = get_session_factory()
    session = session_factory()
    
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        await session.close()


async def init_db():
    """데이터베이스 연결 테스트"""
    from sqlalchemy import text
    
    engine = get_engine()
    
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    
    logger.info("Database connection verified")


async def close_db():
    """데이터베이스 연결 종료"""
    global _engine, _async_session_factory
    
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connection closed")
