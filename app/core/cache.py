"""
간단한 메모리 캐시 (TTL 지원)
"""

import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class CacheEntry:
    """캐시 엔트리"""
    data: Any
    expires_at: float


class MemoryCache:
    """TTL 지원 메모리 캐시"""

    def __init__(self, default_ttl: int = 600):
        """
        Args:
            default_ttl: 기본 만료 시간 (초), 기본값 10분
        """
        self._cache: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl

    def set(self, key: str, data: Any, ttl: int | None = None) -> None:
        """데이터 저장"""
        expires_at = time.time() + (ttl or self._default_ttl)
        self._cache[key] = CacheEntry(data=data, expires_at=expires_at)
        self._cleanup()

    def get(self, key: str) -> Any | None:
        """데이터 조회 (만료된 경우 None)"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.data

    def pop(self, key: str) -> Any | None:
        """데이터 조회 후 삭제"""
        data = self.get(key)
        if data is not None and key in self._cache:
            del self._cache[key]
        return data

    def generate_token(self) -> str:
        """고유 토큰 생성"""
        return str(uuid.uuid4())

    def _cleanup(self) -> None:
        """만료된 엔트리 정리 (100개 초과 시)"""
        if len(self._cache) > 100:
            now = time.time()
            expired_keys = [k for k, v in self._cache.items() if now > v.expires_at]
            for key in expired_keys:
                del self._cache[key]


# 계좌 인증용 글로벌 캐시 인스턴스
account_verify_cache = MemoryCache(default_ttl=600)  # 10분
