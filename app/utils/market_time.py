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

    장 운영 시간: 08:00 ~ 익일 08:00 (KST)
    - 08:00 이후: 당일 장 (프리마켓 + 정규장 + 야간장)
    - 08:00 이전: 전일 야간장 연장
    - 주말(토 08:00 ~ 월 08:00)은 장 마감

    Args:
        check_time: 확인할 시각 (None이면 현재 시각, KST 기준)

    Returns:
        장중이면 True, 아니면 False
    """
    if check_time is None:
        check_time = datetime.now(KST)
    else:
        if check_time.tzinfo is None:
            check_time = check_time.replace(tzinfo=KST)
        elif check_time.tzinfo != KST:
            check_time = check_time.astimezone(KST)

    weekday = check_time.weekday()  # 0=월, 4=금, 5=토, 6=일
    current_time = check_time.time()
    market_start = time(8, 0)

    if current_time >= market_start:
        # 08:00 이후: 당일이 평일(월~금)이면 장중
        return weekday < 5
    else:
        # 08:00 이전: 전일이 평일이면 장중 (야간장 연장)
        # 월요일 08:00 이전 = 일요일 야간 = 장 마감
        prev_weekday = (weekday - 1) % 7
        return prev_weekday < 5


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
