"""
User Repository - DB 접근 레이어
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.database.users import Users


class UserRepository:
    """User DB 접근"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_uid(self, uid: int) -> Users | None:
        """UID로 사용자 조회"""
        result = await self.db.execute(
            select(Users).where(Users.uid == uid)
        )
        return result.scalar_one_or_none()
    
    async def get_by_uid_with_accounts(self, uid: int) -> Users | None:
        """UID로 사용자 조회 (계좌 포함)"""
        result = await self.db.execute(
            select(Users)
            .options(selectinload(Users.accounts))
            .where(Users.uid == uid)
        )
        return result.scalar_one_or_none()
    
    async def get_by_nickname(self, nickname: str) -> Users | None:
        """닉네임으로 사용자 조회"""
        result = await self.db.execute(
            select(Users).where(Users.nickname == nickname)
        )
        return result.scalar_one_or_none()
    
    async def create(self, user: Users) -> Users:
        """사용자 생성"""
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user
    
    async def update(self, user: Users) -> Users:
        """사용자 업데이트"""
        await self.db.flush()
        await self.db.refresh(user)
        return user
