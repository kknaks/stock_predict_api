"""
권한 체크 의존성 (RBAC)
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.enums import UserRole
from app.core.security import decode_token

# Bearer 토큰 스키마
bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload:
    """토큰 페이로드"""
    def __init__(self, uid: int, nickname: str, role: UserRole):
        self.uid = uid
        self.nickname = nickname
        self.role = role


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]
) -> TokenPayload:
    """
    현재 로그인한 사용자 정보 가져오기
    
    Raises:
        HTTPException 401: 인증 실패
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(credentials.credentials)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 토큰 타입 체크
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Token이 필요합니다",
        )
    
    return TokenPayload(
        uid=int(payload.get("sub")),  # 문자열 → 정수 변환
        nickname=payload.get("nickname"),
        role=UserRole(payload.get("role", "user")),
    )


# 타입 힌트용
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


def require_role(*allowed_roles: UserRole):
    """
    특정 역할만 허용하는 의존성 팩토리
    
    Usage:
        @router.get("/admin", dependencies=[Depends(require_role(UserRole.MASTER))])
        async def admin_only():
            ...
    """
    async def role_checker(current_user: CurrentUser) -> TokenPayload:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"권한이 없습니다. 필요한 역할: {[r.value for r in allowed_roles]}",
            )
        return current_user
    
    return role_checker


# 편의용 의존성
RequireMaster = Depends(require_role(UserRole.MASTER))
RequireUser = Depends(require_role(UserRole.USER, UserRole.MASTER))
