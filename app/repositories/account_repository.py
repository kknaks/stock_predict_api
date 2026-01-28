"""
Account Repository - DB 접근 레이어
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, contains_eager
from sqlalchemy.orm.attributes import set_committed_value

from app.database.database.users import Accounts
from app.database.database.strategy import UserStrategy


class AccountRepository:
    """Account DB 접근"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_by_id(self, account_id: int) -> Accounts | None:
        """ID로 계좌 조회"""
        result = await self.db.execute(
            select(Accounts).where(Accounts.id == account_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_account_number(self, account_number: str) -> Accounts | None:
        """계좌번호로 조회"""
        result = await self.db.execute(
            select(Accounts).where(Accounts.account_number == account_number)
        )
        return result.scalar_one_or_none()
    
    async def get_by_user_uid(self, user_uid: int) -> list[Accounts]:
        """사용자의 계좌 목록 조회 (삭제된 계좌 제외)"""
        result = await self.db.execute(
            select(Accounts).where(
                Accounts.user_uid == user_uid,
                Accounts.is_deleted != True,
            )
        )
        return list(result.scalars().all())
    
    async def get_user_account(self, account_id: int, user_uid: int) -> Accounts | None:
        """사용자의 특정 계좌 조회 (삭제된 계좌 제외)"""
        result = await self.db.execute(
            select(Accounts).where(
                Accounts.id == account_id,
                Accounts.user_uid == user_uid,
                Accounts.is_deleted != True,
            )
        )
        return result.scalar_one_or_none()

    async def get_user_account_with_strategies(self, account_id: int, user_uid: int) -> Accounts | None:
        """사용자의 계좌 상세 조회 (전략 포함, 삭제된 계좌/전략 제외)"""
        result = await self.db.execute(
            select(Accounts)
            .where(
                Accounts.id == account_id,
                Accounts.user_uid == user_uid,
                Accounts.is_deleted != True,
            )
            .options(
                selectinload(
                    Accounts.user_strategies.and_(UserStrategy.is_deleted != True)
                ).selectinload(UserStrategy.strategy_info),
                selectinload(
                    Accounts.user_strategies.and_(UserStrategy.is_deleted != True)
                ).selectinload(UserStrategy.strategy_weight_type),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, account: Accounts) -> Accounts:
        """계좌 생성"""
        self.db.add(account)
        await self.db.flush()
        await self.db.refresh(account)
        # lazy loading 방지 - 신규 생성이므로 빈 리스트
        set_committed_value(account, "user_strategies", [])
        return account
    
    async def update(self, account: Accounts) -> Accounts:
        """계좌 업데이트 (토큰 갱신 등)"""
        await self.db.flush()
        await self.db.refresh(account)
        # lazy loading 방지
        set_committed_value(account, "user_strategies", [])
        return account
    
    async def update_balance(self, account: Accounts, amount: float) -> Accounts:
        """계좌 잔액 업데이트 (+/-)"""
        account.account_balance += amount
        await self.db.flush()
        await self.db.refresh(account)
        return account
    
    async def delete(self, account: Accounts) -> None:
        """계좌 삭제"""
        await self.db.delete(account)
