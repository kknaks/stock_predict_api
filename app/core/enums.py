"""
공통 Enum 정의
"""

import enum


class UserRole(str, enum.Enum):
    """사용자 역할 (RBAC)"""
    MASTER = "master"  # 관리자: 모든 권한
    USER = "user"      # 일반 사용자: 제한된 권한
    MOCK = "mock"      # 모의 사용자: 모의 거래


class StrategyStatus(str, enum.Enum):
    """전략 상태"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PAUSED = "paused"
