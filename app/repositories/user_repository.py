"""
User Repository - DB 접근 레이어
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.database.users import Users, Accounts
from app.database.database.strategy import UserStrategy


class UserRepository:
    """User DB 접근"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_uid_with_accounts(self, uid: int) -> Users | None:
        """UID로 사용자 조회 (계좌 및 전략 포함, 삭제된 계좌/전략 제외)"""
        result = await self.db.execute(
            select(Users)
            .options(
                selectinload(
                    Users.accounts.and_(Accounts.is_deleted != True)
                )
                .selectinload(
                    Accounts.user_strategies.and_(UserStrategy.is_deleted != True)
                )
                .selectinload(UserStrategy.strategy_info),
                selectinload(
                    Users.accounts.and_(Accounts.is_deleted != True)
                )
                .selectinload(
                    Accounts.user_strategies.and_(UserStrategy.is_deleted != True)
                )
                .selectinload(UserStrategy.strategy_weight_type),
            )
            .where(Users.uid == uid)
        )
        return result.scalar_one_or_none()

    async def get_account_by_number(self, account_number: str) -> Accounts | None:
        """계좌번호로 계좌 조회"""
        result = await self.db.execute(
            select(Accounts).where(Accounts.account_number == account_number)
        )
        return result.scalar_one_or_none()

    async def create_account(self, account: Accounts) -> Accounts:
        """계좌 생성"""
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account