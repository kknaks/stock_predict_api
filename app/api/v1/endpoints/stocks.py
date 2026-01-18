"""
주식 관련 API 엔드포인트
"""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.core.permissions import CurrentUser
from app.schemas.stocks import (
    CreateStrategyRequest,
    CreateStrategyResponse,
    StrategyInfoDetail,
    UpdateStrategyRequest,
    UpdateStrategyResponse,
)
from app.services.stock_service import StockService

router = APIRouter()


@router.post("/strategy", response_model=CreateStrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    current_user: CurrentUser,
    request: CreateStrategyRequest,
    db: DbSession,
):
    service = StockService(db)

    try:
        user_strategy = await service.create_user_strategy(
            user_id=current_user.uid,
            strategy_id=request.strategy_id,
            ls_ratio=request.ls_ratio,
            tp_ratio=request.tp_ratio,
        )
        return user_strategy
    except ValueError as e:
        if "존재하지 않는" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )

@router.patch("/strategy", response_model=UpdateStrategyResponse, status_code=status.HTTP_200_OK)
async def update_strategy(
    current_user: CurrentUser,
    request: UpdateStrategyRequest,
    db: DbSession,
):
    service = StockService(db)

    try:
        user_strategy = await service.update_user_strategy(
            user_id=current_user.uid,
            strategy_id=request.strategy_id,
            ls_ratio=request.ls_ratio,
            tp_ratio=request.tp_ratio,
            status=request.status.value,
            is_auto=request.is_auto,
        )
        return UpdateStrategyResponse(
            id=user_strategy.id,
            ls_ratio=user_strategy.ls_ratio,
            tp_ratio=user_strategy.tp_ratio,
            status=user_strategy.status,
            is_auto=user_strategy.is_auto,
            strategy_info=StrategyInfoDetail(
                id=user_strategy.strategy_info.id,
                name=user_strategy.strategy_info.name,
                description=user_strategy.strategy_info.description,
            ),
        )
    except ValueError as e:
        if "존재하지 않는" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )