"""
Account Service - 비즈니스 로직 레이어
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import account_verify_cache
from app.database.database.users import Accounts, AccountType
from app.repositories.account_repository import AccountRepository
from app.services.kis_service import KISService

logger = logging.getLogger(__name__)


@dataclass
class VerifiedAccountData:
    """인증된 계좌 정보"""
    account_number: str
    account_type: AccountType
    app_key: str
    app_secret: str
    hts_id: str
    kis_access_token: str | None
    kis_token_expired_at: datetime | None
    account_balance: int


class AccountService:
    """계좌 관련 비즈니스 로직"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AccountRepository(db)

    async def verify_account(
        self,
        account_number: str,
        app_key: str,
        app_secret: str,
        account_type: AccountType,
        hts_id: str,
        exclude_account_id: int | None = None,
    ) -> tuple[str, int]:
        """
        계좌 인증 (REAL/PAPER 전용)

        1. 중복 체크 (수정 시 자기 자신 제외)
        2. KIS API로 토큰 발급 + 잔고 조회
        3. 인증 정보 캐시에 저장
        4. 임시 토큰 + 잔고 반환
        """
        if account_type == AccountType.MOCK:
            raise ValueError("MOCK 계좌는 인증이 필요하지 않습니다")

        # 중복 체크 (수정 시 자기 계좌는 제외)
        existing = await self.repo.get_by_account_number(account_number)
        if existing and existing.id != exclude_account_id:
            raise ValueError("이미 등록된 계좌번호입니다")

        # KIS API 호출
        is_paper = account_type == AccountType.PAPER
        kis = KISService(app_key, app_secret, is_paper)
        try:
            await kis.get_access_token()
            balance_data = await kis.get_account_balance(account_number)

            if balance_data.get("rt_cd") != "0":
                raise ValueError(f"계좌 조회 실패: {balance_data.get('msg1', '알 수 없는 오류')}")

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"KIS API failed: {e}")
            raise ValueError(f"KIS API 오류: {str(e)}")

        # 잔고 추출 (예수금: 거래 가능한 현금 잔고)
        total_balance = 0
        if balance_data.get("output2"):
            # dnca_tot_amt: 예수금 (거래 가능한 현금 잔고, D+2 미수금 포함)
            # tot_evlu_amt: 총평가금액 (보유 주식 평가금액 포함)
            total_balance = int(balance_data["output2"][0].get("dnca_tot_amt", 0))

        # 캐시에 저장
        verified_data = VerifiedAccountData(
            account_number=account_number,
            account_type=account_type,
            app_key=app_key,
            app_secret=app_secret,
            hts_id=hts_id,
            kis_access_token=kis.access_token,
            kis_token_expired_at=kis.token_expired_at,
            account_balance=total_balance,
        )
        verify_token = account_verify_cache.generate_token()
        account_verify_cache.set(verify_token, verified_data)

        return verify_token, total_balance

    async def create_account(
        self,
        user_uid: int,
        account_name: str,
        verify_token: str | None = None,
        account_type: AccountType | None = None,
        account_balance: int | None = None,
    ) -> Accounts:
        """
        계좌 생성

        - verify_token 있으면: 캐시에서 인증 정보 조회 (REAL/PAPER)
        - verify_token 없으면: MOCK 계좌 직접 생성
        """
        if verify_token:
            # REAL/PAPER: 캐시에서 인증 정보 조회
            verified_data: VerifiedAccountData | None = account_verify_cache.pop(verify_token)
            if not verified_data:
                raise ValueError("인증 정보가 만료되었거나 유효하지 않습니다")

            # 중복 체크 (인증 후 다른 사람이 등록했을 수 있음)
            existing = await self.repo.get_by_account_number(verified_data.account_number)
            if existing:
                raise ValueError("이미 등록된 계좌번호입니다")

            account = Accounts(
                user_uid=user_uid,
                account_number=verified_data.account_number,
                account_name=account_name,
                account_type=verified_data.account_type,
                hts_id=verified_data.hts_id,
                account_balance=verified_data.account_balance,
                app_key=verified_data.app_key,
                app_secret=verified_data.app_secret,
                kis_access_token=verified_data.kis_access_token,
                kis_token_expired_at=verified_data.kis_token_expired_at,
            )
        else:
            # MOCK: 직접 생성
            if account_type != AccountType.MOCK:
                raise ValueError("verify_token이 필요합니다")
            if account_balance is None:
                raise ValueError("MOCK 계좌는 초기 잔고가 필요합니다")

            mock_token = account_verify_cache.generate_token()[:8]
            account = Accounts(
                user_uid=user_uid,
                account_number=f"MOCK-{user_uid}-{mock_token}",
                account_name=account_name,
                account_type=AccountType.MOCK,
                hts_id=f"mock_{user_uid}_{mock_token}",
                account_balance=account_balance,
                app_key="mock_app_key",
                app_secret="mock_app_secret",
            )

        return await self.repo.create(account)
    
    async def get_user_accounts(self, user_uid: int) -> list[Accounts]:
        """사용자의 계좌 목록 조회"""
        return await self.repo.get_by_user_uid(user_uid)
    
    async def get_user_account(self, account_id: int, user_uid: int) -> Accounts | None:
        """사용자의 특정 계좌 조회"""
        return await self.repo.get_user_account(account_id, user_uid)

    async def get_account_detail(self, account_id: int, user_uid: int) -> Accounts | None:
        """사용자의 계좌 상세 조회 (전략 포함)"""
        return await self.repo.get_user_account_with_strategies(account_id, user_uid)

    async def delete_account(self, account_id: int, user_uid: int) -> bool:
        """
        계좌 삭제 (soft delete)

        - is_deleted = True
        - 민감 정보 초기화 (hts_id, app_key, app_secret, kis_access_token, kis_token_expired_at)
        """
        account = await self.repo.get_user_account(account_id, user_uid)
        if not account:
            return False

        deleted_suffix = f"deleted_{account_verify_cache.generate_token()[:8]}"
        account.is_deleted = True
        account.hts_id = deleted_suffix
        account.app_key = deleted_suffix
        account.app_secret = deleted_suffix
        account.kis_access_token = None
        account.kis_token_expired_at = None

        await self.repo.update(account)
        return True

    async def update_account(
        self,
        account_id: int,
        user_uid: int,
        account_name: str | None = None,
        account_balance: int | None = None,
        verify_token: str | None = None,
    ) -> Accounts:
        """
        계좌 수정

        - MOCK: account_name, account_balance 수정 가능
        - REAL/PAPER: account_name만 수정 가능 (인증 정보 수정 시 verify_token 필요)
        """
        account = await self.repo.get_user_account(account_id, user_uid)
        if not account:
            raise ValueError("계좌를 찾을 수 없습니다")

        # verify_token이 있으면 인증 정보 업데이트 (REAL/PAPER)
        if verify_token:
            if account.account_type == AccountType.MOCK:
                raise ValueError("MOCK 계좌는 인증 정보를 수정할 수 없습니다")

            verified_data: VerifiedAccountData | None = account_verify_cache.pop(verify_token)
            if not verified_data:
                raise ValueError("인증 정보가 만료되었거나 유효하지 않습니다")

            # 인증 정보 업데이트
            account.account_number = verified_data.account_number
            account.app_key = verified_data.app_key
            account.app_secret = verified_data.app_secret
            account.hts_id = verified_data.hts_id
            account.kis_access_token = verified_data.kis_access_token
            account.kis_token_expired_at = verified_data.kis_token_expired_at
            account.account_balance = verified_data.account_balance

        # account_name 수정
        if account_name is not None:
            account.account_name = account_name

        # account_balance 수정 (MOCK만)
        if account_balance is not None:
            if account.account_type != AccountType.MOCK:
                raise ValueError("잔고는 MOCK 계좌만 수정 가능합니다")
            account.account_balance = account_balance

        return await self.repo.update(account)

    async def get_valid_kis_token(self, account: Accounts) -> str:
        """
        유효한 KIS 토큰 반환 (만료 시 자동 갱신)
        
        - 토큰이 유효하면 그대로 반환
        - 만료됐으면 갱신 후 DB 저장하고 반환
        """
        if account.is_token_valid():
            return account.kis_access_token
        
        # 토큰 갱신
        logger.info(f"Refreshing KIS token for account {account.id}")
        
        kis = KISService(account.app_key, account.app_secret)
        await kis.get_access_token()
        
        # DB 업데이트
        account.kis_access_token = kis.access_token
        account.kis_token_expired_at = kis.token_expired_at
        await self.repo.update(account)
        
        logger.info(f"KIS token refreshed for account {account.id}")
        return account.kis_access_token
    
    async def get_account_balance(self, account: Accounts) -> dict:
        """계좌 잔고 조회 (토큰 자동 갱신)"""
        token = await self.get_valid_kis_token(account)
        
        kis = KISService(account.app_key, account.app_secret)
        kis.access_token = token
        
        return await kis.get_account_balance(account.account_number)
