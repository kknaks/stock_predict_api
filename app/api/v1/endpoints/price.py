"""
실시간 가격 SSE 엔드포인트 및 시간봉/분봉 조회 API
"""

import asyncio
import json
import logging
from datetime import date
from typing import Set, Optional

from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.price_cache import get_price_cache
from app.services.candle_service import CandleService
from app.config.db_connections import get_db
from app.utils.market_time import is_market_open

logger = logging.getLogger(__name__)

router = APIRouter()

# 연결된 클라이언트 관리: {client_id: set(stock_codes)}
_connected_clients: dict[str, Set[str]] = {}
_client_counter = 0


def format_sse_event(event: str, data: dict) -> str:
    """SSE 이벤트 포맷팅"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/market/status")
async def get_market_status():
    """시장 상태 조회"""
    return is_market_open()

@router.get("/stream")
async def stream_price_updates(
    stock_codes: str = Query(..., description="구독할 종목 코드들 (쉼표로 구분, 예: 005930,000660)"),
):
    """
    실시간 가격 업데이트 SSE 스트리밍

    Args:
        stock_codes: 구독할 종목 코드들 (쉼표로 구분)

    Returns:
        SSE 스트리밍 응답
    """
    global _client_counter

    # 클라이언트 ID 생성
    client_id = f"client_{_client_counter}"
    _client_counter += 1

    # 종목 코드 파싱
    subscribed_stocks = set([code.strip() for code in stock_codes.split(",") if code.strip()])
    _connected_clients[client_id] = subscribed_stocks

    logger.info(f"SSE client connected: {client_id}, stocks: {subscribed_stocks}")

    price_cache = get_price_cache()

    async def event_generator():
        """SSE 이벤트 생성기"""
        try:
            # 초기 가격 전송 (전체 데이터)
            for stock_code in subscribed_stocks:
                cached_price = price_cache.get(stock_code)
                if cached_price:
                    data = cached_price.model_dump()
                    data["timestamp"] = cached_price.timestamp.isoformat()
                    yield format_sse_event("price_update", data)

            # 주기적으로 가격 체크 및 업데이트 전송
            last_prices = {}
            for stock_code in subscribed_stocks:
                cached_price = price_cache.get(stock_code)
                if cached_price:
                    last_prices[stock_code] = cached_price.current_price

            while True:
                await asyncio.sleep(1)  # 1초마다 체크

                # 연결이 끊어졌는지 확인
                if client_id not in _connected_clients:
                    break

                # 각 종목의 가격 변경 확인
                for stock_code in subscribed_stocks:
                    cached_price = price_cache.get(stock_code)
                    if cached_price:
                        current_price = cached_price.current_price
                        last_price = last_prices.get(stock_code)

                        # 가격이 변경되었거나 처음이면 전송 (전체 데이터)
                        if last_price != current_price or stock_code not in last_prices:
                            last_prices[stock_code] = current_price
                            data = cached_price.model_dump()
                            data["timestamp"] = cached_price.timestamp.isoformat()
                            yield format_sse_event("price_update", data)

        except asyncio.CancelledError:
            logger.info(f"SSE client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"SSE event generator error: {e}", exc_info=True)
        finally:
            # 클라이언트 제거
            if client_id in _connected_clients:
                del _connected_clients[client_id]
                logger.info(f"SSE client removed: {client_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 비활성화
        }
    )


# ========================
# 시간봉 API
# ========================

@router.get("/candles/{stock_code}/hours")
async def get_hour_candles(
    stock_code: str,
    start_date: Optional[date] = Query(None, description="시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="종료 날짜 (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """특정 종목의 시간봉 데이터 조회"""
    if start_date is None:
        start_date = date.today()
    if end_date is None:
        end_date = date.today()

    try:
        service = CandleService(db)
        return await service.get_hour_candles(stock_code, start_date, end_date)
    except Exception as e:
        logger.error(f"Error fetching hour candles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candles/{stock_code}/hours/today")
async def get_today_hour_candles(
    stock_code: str,
    db: AsyncSession = Depends(get_db),
):
    """특정 종목의 오늘 시간봉 데이터 조회 (DB + 캐시 실시간)"""
    try:
        service = CandleService(db)
        return await service.get_today_hour_candles(stock_code)
    except Exception as e:
        logger.error(f"Error fetching today's hour candles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# 분봉 API
# ========================

@router.get("/candles/{stock_code}/minutes/today")
async def get_today_minute_candles(
    stock_code: str,
    minute_interval: int = Query(1, description="분봉 간격 (1, 3, 5, 10, 15, 30)"),
    db: AsyncSession = Depends(get_db),
):
    """특정 종목의 오늘 분봉 데이터 조회 (DB + 캐시 실시간)"""
    try:
        service = CandleService(db)
        return await service.get_today_minute_candles(stock_code, minute_interval)
    except Exception as e:
        logger.error(f"Error fetching today's minute candles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candles/{stock_code}/minutes")
async def get_minute_candles(
    stock_code: str,
    start_date: Optional[date] = Query(None, description="시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="종료 날짜 (YYYY-MM-DD)"),
    minute_interval: int = Query(1, description="분봉 간격 (1, 3, 5, 10, 15, 30)"),
    db: AsyncSession = Depends(get_db),
):
    """특정 종목의 분봉 데이터 조회"""
    if start_date is None:
        start_date = date.today()
    if end_date is None:
        end_date = date.today()

    try:
        service = CandleService(db)
        return await service.get_minute_candles(stock_code, start_date, end_date, minute_interval)
    except Exception as e:
        logger.error(f"Error fetching minute candles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
