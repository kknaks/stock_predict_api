"""
보안 관련 유틸리티

JWT 토큰 생성/검증, 비밀번호 해싱 (SHA-256)
"""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import settings


def hash_password(password: str) -> str:
    """비밀번호 SHA-256 해싱"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """비밀번호 검증"""
    return hash_password(plain_password) == hashed_password


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """
    Access Token 생성
    
    Args:
        data: 토큰에 담을 데이터 (sub, role 등)
        expires_delta: 만료 시간
    
    Returns:
        JWT 토큰 문자열
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire, "type": "access"})
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(data: dict[str, Any]) -> str:
    """
    Refresh Token 생성
    
    Args:
        data: 토큰에 담을 데이터
    
    Returns:
        JWT 토큰 문자열
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})
    
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any] | None:
    """
    토큰 디코딩
    
    Args:
        token: JWT 토큰
    
    Returns:
        디코딩된 payload 또는 None (실패 시)
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None
