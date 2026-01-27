"""
API 호출 속도 제한 모듈

초당 최대 호출 횟수를 제한하여 API rate limit 준수
- REAL 계좌: 초당 20건
- PAPER 계좌: 초당 2건
"""

import time
import asyncio
from typing import Callable
from functools import wraps


class RateLimiter:
    """
    API 호출 속도 제한 (Token Bucket 알고리즘)

    초당 최대 호출 횟수를 제한
    """

    def __init__(self, max_calls: int = 20, time_window: float = 1.0):
        """
        Args:
            max_calls: 시간 창 내 최대 호출 횟수 (기본 20)
            time_window: 시간 창 (초, 기본 1.0초)
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.call_times = []

    def __call__(self, func: Callable) -> Callable:
        """동기 함수용 데코레이터"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            self._wait_if_needed()
            return func(*args, **kwargs)
        return wrapper

    def async_decorator(self, func: Callable) -> Callable:
        """비동기 함수용 데코레이터"""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            await self._wait_if_needed_async()
            return await func(*args, **kwargs)
        return wrapper

    def _wait_if_needed(self):
        """필요 시 대기 (동기)"""
        now = time.time()
        self.call_times = [t for t in self.call_times if now - t < self.time_window]

        if len(self.call_times) >= self.max_calls:
            sleep_time = self.time_window - (now - self.call_times[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
                now = time.time()
                self.call_times = [t for t in self.call_times if now - t < self.time_window]

        self.call_times.append(time.time())

    async def _wait_if_needed_async(self):
        """필요 시 대기 (비동기)"""
        now = time.time()
        self.call_times = [t for t in self.call_times if now - t < self.time_window]

        if len(self.call_times) >= self.max_calls:
            sleep_time = self.time_window - (now - self.call_times[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                now = time.time()
                self.call_times = [t for t in self.call_times if now - t < self.time_window]

        self.call_times.append(time.time())


# 계좌별 rate limiter 관리
_account_rate_limiters: dict[int, RateLimiter] = {}


def get_account_rate_limiter(account_id: int, is_paper: bool) -> RateLimiter:
    """
    계좌별 rate limiter 반환

    Args:
        account_id: 계좌 ID
        is_paper: PAPER 계좌 여부 (True: 초당 2건, False: 초당 20건)
    """
    global _account_rate_limiters
    if account_id not in _account_rate_limiters:
        max_calls = 2 if is_paper else 20
        _account_rate_limiters[account_id] = RateLimiter(max_calls=max_calls, time_window=1.0)
    return _account_rate_limiters[account_id]
