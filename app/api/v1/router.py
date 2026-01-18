"""
API v1 라우터 통합
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, users, stocks

api_router = APIRouter()

# 라우터 등록
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["Stocks"])

# 추가 라우터 예시:
# from app.api.v1.endpoints import stocks, predictions
# api_router.include_router(stocks.router, prefix="/stocks", tags=["Stocks"])
# api_router.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
