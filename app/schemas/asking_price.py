"""
실시간 호가 데이터 스키마
"""

from datetime import datetime
from pydantic import BaseModel


class AskingPriceMessage(BaseModel):
    """실시간 호가 데이터 메시지 (H0STASP0)"""

    timestamp: datetime

    # 기본 정보
    stock_code: str           # MKSC_SHRN_ISCD: 종목코드
    business_hour: str        # BSOP_HOUR: 영업시간
    hour_cls_code: str        # HOUR_CLS_CODE: 시간구분코드

    # 매도호가 1~10
    askp1: str
    askp2: str
    askp3: str
    askp4: str
    askp5: str
    askp6: str
    askp7: str
    askp8: str
    askp9: str
    askp10: str

    # 매수호가 1~10
    bidp1: str
    bidp2: str
    bidp3: str
    bidp4: str
    bidp5: str
    bidp6: str
    bidp7: str
    bidp8: str
    bidp9: str
    bidp10: str

    # 매도호가잔량 1~10
    askp_rsqn1: str
    askp_rsqn2: str
    askp_rsqn3: str
    askp_rsqn4: str
    askp_rsqn5: str
    askp_rsqn6: str
    askp_rsqn7: str
    askp_rsqn8: str
    askp_rsqn9: str
    askp_rsqn10: str

    # 매수호가잔량 1~10
    bidp_rsqn1: str
    bidp_rsqn2: str
    bidp_rsqn3: str
    bidp_rsqn4: str
    bidp_rsqn5: str
    bidp_rsqn6: str
    bidp_rsqn7: str
    bidp_rsqn8: str
    bidp_rsqn9: str
    bidp_rsqn10: str

    # 총 잔량
    total_askp_rsqn: str      # 총매도호가잔량
    total_bidp_rsqn: str      # 총매수호가잔량
    ovtm_total_askp_rsqn: str # 시간외총매도호가잔량
    ovtm_total_bidp_rsqn: str # 시간외총매수호가잔량

    # 예상체결 정보
    antc_cnpr: str            # 예상체결가
    antc_cnqn: str            # 예상체결량
    antc_vol: str             # 예상체결대금
    antc_cntg_vrss: str       # 예상체결전일대비
    antc_cntg_vrss_sign: str  # 예상체결전일대비부호
    antc_cntg_prdy_ctrt: str  # 예상체결전일대비율

    # 기타
    acml_vol: str             # 누적거래량
    total_askp_rsqn_icdc: str # 총매도호가잔량증감
    total_bidp_rsqn_icdc: str # 총매수호가잔량증감
    ovtm_total_askp_icdc: str # 시간외총매도호가잔량증감
    ovtm_total_bidp_icdc: str # 시간외총매수호가잔량증감
    stck_deal_cls_code: str   # 주식거래구분코드
