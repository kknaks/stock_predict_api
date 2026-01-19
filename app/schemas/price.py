"""
실시간 가격 데이터 스키마
"""

from datetime import datetime
from pydantic import BaseModel


class PriceMessage(BaseModel):
    """실시간 가격 데이터 메시지"""

    timestamp: datetime
    stock_code: str  # MKSC_SHRN_ISCD
    trade_time: str  # STCK_CNTG_HOUR
    current_price: str  # STCK_PRPR
    price_change_sign: str  # PRDY_VRSS_SIGN
    price_change: str  # PRDY_VRSS
    price_change_rate: str  # PRDY_CTRT
    weighted_avg_price: str  # WGHN_AVRG_STCK_PRC
    open_price: str  # STCK_OPRC
    high_price: str  # STCK_HGPR
    low_price: str  # STCK_LWPR
    ask_price1: str  # ASKP1
    bid_price1: str  # BIDP1
    trade_volume: str  # CNTG_VOL
    accumulated_volume: str  # ACML_VOL
    accumulated_trade_amount: str  # ACML_TR_PBMN
    sell_trade_count: str  # SELN_CNTG_CSNU
    buy_trade_count: str  # SHNU_CNTG_CSNU
    net_buy_trade_count: str  # NTBY_CNTG_CSNU
    trade_strength: str  # CTTR
    total_sell_trade_volume: str  # SELN_CNTG_SMTN
    total_buy_trade_volume: str  # SHNU_CNTG_SMTN
    trade_type: str  # CCLD_DVSN
    buy_rate: str  # SHNU_RATE
    volume_ratio: str  # PRDY_VOL_VRSS_ACML_VOL_RATE
    open_time: str  # OPRC_HOUR
    open_price_change_sign: str  # OPRC_VRSS_PRPR_SIGN
    open_price_change: str  # OPRC_VRSS_PRPR
    high_time: str  # HGPR_HOUR
    high_price_change_sign: str  # HGPR_VRSS_PRPR_SIGN
    high_price_change: str  # HGPR_VRSS_PRPR
    low_time: str  # LWPR_HOUR
    low_price_change_sign: str  # LWPR_VRSS_PRPR_SIGN
    low_price_change: str  # LWPR_VRSS_PRPR
    business_date: str  # BSOP_DATE
    new_market_open_code: str  # NEW_MKOP_CLS_CODE
    trading_halt_yn: str  # TRHT_YN
    ask_remaining1: str  # ASKP_RSQN1
    bid_remaining1: str  # BIDP_RSQN1
    total_ask_remaining: str  # TOTAL_ASKP_RSQN
    total_bid_remaining: str  # TOTAL_BIDP_RSQN
    volume_turnover_rate: str  # VOL_TNRT
    prev_same_time_volume: str  # PRDY_SMNS_HOUR_ACML_VOL
    prev_same_time_volume_rate: str  # PRDY_SMNS_HOUR_ACML_VOL_RATE
    time_class_code: str  # HOUR_CLS_CODE
    market_trade_class_code: str  # MRKT_TRTM_CLS_CODE
    vi_standard_price: str  # VI_STND_PRC
