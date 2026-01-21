"""
실시간 가격 SSE 엔드포인트 및 시간봉 조회 API
"""

import asyncio
import json
import logging
from datetime import date, datetime
from typing import Set, List, Optional

from fastapi import APIRouter, Query, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.price_cache import get_price_cache
from app.config.db_connections import get_db
from app.handler.price_handler import aggregate_ticks_to_candle

# stock_predict_database 모델 import
try:
    from database.strategy import HourCandleData
except ImportError:
    HourCandleData = None

logger = logging.getLogger(__name__)

router = APIRouter()

# 연결된 클라이언트 관리: {client_id: set(stock_codes)}
_connected_clients: dict[str, Set[str]] = {}
_client_counter = 0


def format_sse_event(event: str, data: dict) -> str:
    """SSE 이벤트 포맷팅"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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


@router.get("/candles/{stock_code}")
async def get_hour_candles(
    stock_code: str,
    start_date: Optional[date] = Query(None, description="시작 날짜 (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="종료 날짜 (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    특정 종목의 시간봉 데이터 조회

    Args:
        stock_code: 종목 코드
        start_date: 시작 날짜 (기본값: 오늘)
        end_date: 종료 날짜 (기본값: 오늘)

    Returns:
        시간봉 데이터 리스트
    """
    if HourCandleData is None:
        raise HTTPException(status_code=500, detail="HourCandleData model not available")

    # 기본값 설정
    if start_date is None:
        start_date = date.today()
    if end_date is None:
        end_date = date.today()

    try:
        # 쿼리 실행
        stmt = (
            select(HourCandleData)
            .where(HourCandleData.stock_code == stock_code)
            .where(HourCandleData.candle_date >= start_date)
            .where(HourCandleData.candle_date <= end_date)
            .order_by(HourCandleData.candle_date, HourCandleData.hour)
        )

        result = await db.execute(stmt)
        candles = result.scalars().all()

        return {
            "stock_code": stock_code,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "count": len(candles),
            "candles": [
                {
                    "candle_date": c.candle_date.isoformat(),
                    "hour": c.hour,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "trade_count": c.trade_count,
                }
                for c in candles
            ],
        }

    except Exception as e:
        logger.error(f"Error fetching hour candles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/candles/{stock_code}/today")
async def get_today_hour_candles(
    stock_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    특정 종목의 오늘 시간봉 데이터 조회 (DB + 캐시)

    DB에서 이전 시간봉 데이터 + 캐시에서 현재 시간 실시간 데이터를 합쳐서 반환

    Args:
        stock_code: 종목 코드

    Returns:
        시간봉 데이터 리스트
    """
    price_cache = get_price_cache()
    today = date.today()

    all_candles = []
    db_hours = set()

    # 1. DB에서 오늘 저장된 시간봉 조회
    if HourCandleData is not None:
        try:
            stmt = (
                select(HourCandleData)
                .where(HourCandleData.stock_code == stock_code)
                .where(HourCandleData.candle_date == today)
                .order_by(HourCandleData.hour)
            )

            result = await db.execute(stmt)
            db_candles = result.scalars().all()

            for c in db_candles:
                all_candles.append({
                    "candle_date": c.candle_date.isoformat(),
                    "hour": c.hour,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "trade_count": c.trade_count,
                })
                db_hours.add(c.hour)

        except Exception as e:
            logger.error(f"Error fetching today's hour candles from DB: {e}", exc_info=True)

    # 2. 캐시에서 현재 시간 틱 데이터 조회 및 시간봉 계산
    current_hour = price_cache.get_current_hour()
    ticks = price_cache.get_ticks(stock_code)

    if ticks and current_hour is not None and current_hour not in db_hours:
        # 캐시에 있는 현재 시간 데이터로 시간봉 계산
        candle = aggregate_ticks_to_candle(stock_code, ticks, today, current_hour)
        if candle:
            candle["candle_date"] = today.isoformat()
            all_candles.append(candle)

    # 시간순 정렬
    all_candles.sort(key=lambda x: x["hour"])

    return {
        "stock_code": stock_code,
        "date": today.isoformat(),
        "source": "db+cache" if db_hours and ticks else ("database" if db_hours else ("cache" if ticks else "none")),
        "current_hour": current_hour,
        "count": len(all_candles),
        "candles": all_candles,
    }
