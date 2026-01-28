"""
장중 여부 판단 유틸리티
"""

from datetime import datetime, time, date
from typing import Optional
from zoneinfo import ZoneInfo


# 한국 시간대 (KST, UTC+9)
KST = ZoneInfo("Asia/Seoul")


def is_market_open(check_time: Optional[datetime] = None) -> bool:
    """
    장중 여부 확인
    
    한국 주식시장: 평일 09:00 ~ 15:30 (KST)
    
    Args:
        check_time: 확인할 시각 (None이면 현재 시각, KST 기준)
    
    Returns:
        장중이면 True, 아니면 False
    """
    if check_time is None:
        # 현재 시각을 KST로 가져오기
        check_time = datetime.now(KST)
    else:
        # check_time이 timezone-aware가 아니면 KST로 변환
        if check_time.tzinfo is None:
            check_time = check_time.replace(tzinfo=KST)
        # 다른 timezone이면 KST로 변환
        elif check_time.tzinfo != KST:
            check_time = check_time.astimezone(KST)
    
    # 주말 체크 (토요일=5, 일요일=6)
    if check_time.weekday() >= 5:
        return False
    
    # 시간 체크 (09:00 ~ 15:30)
    market_open = time(9, 0)
    market_close = time(15, 30)
    current_time = check_time.time()
    
    return market_open <= current_time <= market_close


def is_today(check_date: str) -> bool:
    """
    날짜가 오늘인지 확인
    
    Args:
        check_date: 확인할 날짜 (YYYY-MM-DD 형식)
    
    Returns:
        오늘이면 True, 아니면 False
    """
    today = date.today()
    try:
        check = datetime.strptime(check_date, "%Y-%m-%d").date()
        return check == today
    except ValueError:
        return False
