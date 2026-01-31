"""
API v1 라우터 통합
"""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, users, stocks, predict, price, td_position, history, strategy, order, report

api_router = APIRouter()

# 라우터 등록
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["Stocks"])
api_router.include_router(predict.router, prefix="/predict", tags=["Predict"])
api_router.include_router(price.router, prefix="/price", tags=["Price"])
api_router.include_router(td_position.router, prefix="/td-position", tags=["TD Position"])
api_router.include_router(history.router, prefix="/history", tags=["History"])
api_router.include_router(strategy.router, prefix="/strategy", tags=["Strategy"])
api_router.include_router(order.router, prefix="/order", tags=["Order"])
api_router.include_router(report.router, prefix="/reports", tags=["Reports"])
# 추가 라우터 예시:
# from app.api.v1.endpoints import stocks, predictions
# api_router.include_router(stocks.router, prefix="/stocks", tags=["Stocks"])
# api_router.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
