"""
Account Service - 비즈니스 로직 레이어
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.database.users import Accounts
from app.repositories.account_repository import AccountRepository
from app.services.kis_service import KISService

logger = logging.getLogger(__name__)


class AccountService:
    """계좌 관련 비즈니스 로직"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AccountRepository(db)
    
    async def create_account(
        self,
        user_uid: int,
        account_number: str,
        app_key: str,
        app_secret: str,
        is_paper: bool = False,
    ) -> Accounts:
        """
        계좌 등록
        
        1. 중복 체크
        2. KIS 토큰 발급
        3. 계좌 유효성 검증
        4. DB 저장
        """
        # 중복 체크
        existing = await self.repo.get_by_account_number(account_number)
        if existing:
            raise ValueError("이미 등록된 계좌번호입니다")
        
        # KIS 토큰 발급 + 잔고 조회 (유효성 검증 겸)
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
        
        # 잔고 추출 (output2의 tot_evlu_amt = 총평가금액)
        total_balance = 0
        if balance_data.get("output2"):
            total_balance = int(balance_data["output2"][0].get("tot_evlu_amt", 0))
        
        # 계좌 생성
        account = Accounts(
            user_uid=user_uid,
            account_number=account_number,
            account_balance=total_balance,
            app_key=app_key,
            app_secret=app_secret,
            kis_access_token=kis.access_token,
            kis_token_expired_at=kis.token_expired_at,
        )
        
        return await self.repo.create(account)
    
    async def get_user_accounts(self, user_uid: int) -> list[Accounts]:
        """사용자의 계좌 목록 조회"""
        return await self.repo.get_by_user_uid(user_uid)
    
    async def get_user_account(self, account_id: int, user_uid: int) -> Accounts | None:
        """사용자의 특정 계좌 조회"""
        return await self.repo.get_user_account(account_id, user_uid)
    
    async def delete_account(self, account_id: int, user_uid: int) -> bool:
        """계좌 삭제"""
        account = await self.repo.get_user_account(account_id, user_uid)
        if not account:
            return False
        
        await self.repo.delete(account)
        return True
    
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
