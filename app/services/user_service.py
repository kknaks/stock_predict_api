"""
User Service - 비즈니스 로직 레이어
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database.users import Users, Accounts, AccountType
from app.repositories.user_repository import UserRepository
from app.schemas.users import CreateAccountRequest


class UserService:
    """사용자 관련 비즈니스 로직"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)

    async def get_user_with_accounts(self, uid: int) -> Users | None:
        """사용자 정보 조회 (계좌 및 전략 포함)"""
        return await self.repo.get_by_uid_with_accounts(uid)

    async def check_account_exists(self, account_number: str) -> bool:
        """계좌번호 중복 확인"""
        account = await self.repo.get_account_by_number(account_number)
        return account is not None

    async def create_account(self, uid: int, request: CreateAccountRequest) -> Accounts:
        """계좌 생성"""
        account = Accounts(
            user_uid=uid,
            account_number=request.account_number,
            app_key=request.app_key,
            app_secret=request.app_secret,
            account_type=AccountType.PAPER if request.is_paper else AccountType.REAL,
        )
        return await self.repo.create_account(account)
