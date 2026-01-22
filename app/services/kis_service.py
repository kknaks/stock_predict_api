"""
한국투자증권 API 서비스
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)

# KIS API Base URLs
KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"  # 실전
KIS_PAPER_URL = "https://openapivts.koreainvestment.com:29443"  # 모의


class KISService:
    """한국투자증권 API 클라이언트"""
    
    def __init__(self, app_key: str, app_secret: str, is_paper: bool = False):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = KIS_PAPER_URL if is_paper else KIS_BASE_URL
        self.access_token: str | None = None
        self.token_expired_at: datetime | None = None
    
    async def get_access_token(self) -> dict:
        """
        Access Token 발급
        
        Returns:
            {
                "access_token": "...",
                "token_type": "Bearer",
                "expires_in": 86400,
                "access_token_token_expired": "2024-01-01 12:00:00"
            }
        """
        url = f"{self.base_url}/oauth2/tokenP"
        
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        
        # 공식 API 예제에 맞춘 헤더 설정
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            
            # 403 에러 시 상세 정보 로깅
            if response.status_code == 403:
                logger.error(
                    f"KIS API 403 Forbidden - URL: {url}, "
                    f"AppKey: {self.app_key[:10]}..., "
                    f"Response: {response.text}"
                )
                raise ValueError(
                    f"KIS API 인증 실패 (403 Forbidden): "
                    f"app_key/app_secret이 잘못되었거나 환경(실전/모의)이 일치하지 않습니다. "
                    f"Response: {response.text}"
                )
            
            response.raise_for_status()
            data = response.json()
        
        self.access_token = data.get("access_token")
        
        # 만료 시간 파싱
        expired_str = data.get("access_token_token_expired")
        if expired_str:
            self.token_expired_at = datetime.strptime(
                expired_str, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
        
        logger.info("KIS access token issued")
        return data
    
    async def get_account_balance(self, account_number: str) -> dict:
        """
        계좌 잔고 조회
        
        Args:
            account_number: 계좌번호 (8자리-2자리)
        
        Returns:
            계좌 잔고 정보
        """
        if not self.access_token:
            await self.get_access_token()
        
        # 계좌번호 분리 (12345678-01 -> CANO=12345678, ACNT_PRDT_CD=01)
        cano, acnt_prdt_cd = account_number.split("-")
        
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        
        headers = {
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": "TTTC8434R",  # 실전: TTTC8434R, 모의: VTTC8434R
        }
        
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
        
        return data
    
    async def verify_account(self, account_number: str) -> bool:
        """
        계좌 유효성 검증
        
        Args:
            account_number: 계좌번호
        
        Returns:
            유효 여부
        """
        try:
            result = await self.get_account_balance(account_number)
            # rt_cd가 "0"이면 성공
            return result.get("rt_cd") == "0"
        except Exception as e:
            logger.error(f"Account verification failed: {e}")
            return False


async def create_kis_service(app_key: str, app_secret: str, is_paper: bool = False) -> KISService:
    """
    KIS 서비스 생성 및 토큰 발급
    """
    service = KISService(app_key, app_secret, is_paper)
    await service.get_access_token()
    return service
