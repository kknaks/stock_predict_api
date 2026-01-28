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
from app.services.asking_price_cache import get_asking_price_cache
from app.services.candle_service import CandleService
from app.repositories.predict_repository import PredictRepository
from app.schemas.price import StockPriceResponse
from app.config.db_connections import get_db
from app.utils.market_time import is_market_open, is_today

logger = logging.getLogger(__name__)

router = APIRouter()

# 연결된 클라이언트 관리: {client_id: set(stock_codes)}
_connected_clients: dict[str, Set[str]] = {}
_asking_price_clients: dict[str, Set[str]] = {}
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
# 호가 API
# ========================

@router.get("/asking-price/stream")
async def stream_asking_price_updates(
    stock_codes: str = Query(..., description="구독할 종목 코드들 (쉼표로 구분, 예: 005930,000660)"),
):
    """
    실시간 호가 업데이트 SSE 스트리밍

    Args:
        stock_codes: 구독할 종목 코드들 (쉼표로 구분)

    Returns:
        SSE 스트리밍 응답
    """
    global _client_counter

    # 클라이언트 ID 생성
    client_id = f"asking_price_client_{_client_counter}"
    _client_counter += 1

    # 종목 코드 파싱
    subscribed_stocks = set([code.strip() for code in stock_codes.split(",") if code.strip()])
    _asking_price_clients[client_id] = subscribed_stocks

    logger.info(f"Asking price SSE client connected: {client_id}, stocks: {subscribed_stocks}")

    asking_price_cache = get_asking_price_cache()

    async def event_generator():
        """SSE 이벤트 생성기"""
        try:
            # 초기 호가 전송
            for stock_code in subscribed_stocks:
                cached = asking_price_cache.get(stock_code)
                if cached:
                    data = cached.model_dump()
                    data["timestamp"] = cached.timestamp.isoformat()
                    yield format_sse_event("asking_price_update", data)

            # 주기적으로 호가 체크 및 업데이트 전송
            last_askp1: dict[str, str] = {}
            for stock_code in subscribed_stocks:
                cached = asking_price_cache.get(stock_code)
                if cached:
                    last_askp1[stock_code] = cached.askp1

            while True:
                await asyncio.sleep(0.5)  # 0.5초마다 체크 (호가는 변동이 잦음)

                # 연결이 끊어졌는지 확인
                if client_id not in _asking_price_clients:
                    break

                # 각 종목의 호가 변경 확인
                for stock_code in subscribed_stocks:
                    cached = asking_price_cache.get(stock_code)
                    if cached:
                        current_askp1 = cached.askp1
                        last = last_askp1.get(stock_code)

                        # 매도1호가가 변경되었거나 처음이면 전송
                        if last != current_askp1 or stock_code not in last_askp1:
                            last_askp1[stock_code] = current_askp1
                            data = cached.model_dump()
                            data["timestamp"] = cached.timestamp.isoformat()
                            yield format_sse_event("asking_price_update", data)

        except asyncio.CancelledError:
            logger.info(f"Asking price SSE client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"Asking price SSE event generator error: {e}", exc_info=True)
        finally:
            # 클라이언트 제거
            if client_id in _asking_price_clients:
                del _asking_price_clients[client_id]
                logger.info(f"Asking price SSE client removed: {client_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/asking-price/{stock_code}/best")
async def get_best_asking_price(stock_code: str):
    """
    특정 종목의 최우선 호가 조회 (매도1호가, 매수1호가)

    Args:
        stock_code: 종목 코드

    Returns:
        최우선 호가 데이터
    """
    asking_price_cache = get_asking_price_cache()
    best = asking_price_cache.get_best_prices(stock_code)

    if not best:
        raise HTTPException(status_code=404, detail=f"Asking price not found for {stock_code}")

    return {"stock_code": stock_code, **best}


@router.get("/asking-price/{stock_code}")
async def get_asking_price(stock_code: str):
    """
    특정 종목의 현재 호가 조회

    Args:
        stock_code: 종목 코드

    Returns:
        호가 데이터
    """
    asking_price_cache = get_asking_price_cache()
    cached = asking_price_cache.get(stock_code)

    if not cached:
        raise HTTPException(status_code=404, detail=f"Asking price not found for {stock_code}")

    data = cached.model_dump()
    data["timestamp"] = cached.timestamp.isoformat()
    return data


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


# ========================
# 종목 가격 조회 API
# ========================

@router.get("/sell/{stock_code}", response_model=StockPriceResponse)
async def get_stock_price(
    stock_code: str,
    date: str = Query(..., description="날짜 (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """
    특정 종목의 가격 조회 (예측 대상 종목)

    - 오늘 + 장중: 실시간 현재가
    - 오늘 + 장마감 / 과거: 종가
    """
    # 오늘 + 장중인 경우: price_cache에서 실시간 데이터
    if is_today(date) and is_market_open():
        price_cache = get_price_cache()
        cached = price_cache.get(stock_code)

        if cached:
            return StockPriceResponse(
                stock_code=stock_code,
                open_price=int(cached.open_price),
                current_price=int(cached.current_price),
                is_market_open=True,
            )
        # 캐시에 없으면 DB에서 조회 (아래로 fall through)

    # 오늘 + 장마감 또는 과거: GapPredictions에서 조회
    repo = PredictRepository(db)
    prediction = await repo.get_prediction_by_stock_and_date(stock_code, date)

    if not prediction:
        raise HTTPException(
            status_code=404,
            detail=f"Prediction not found for {stock_code} on {date}"
        )

    # actual_close가 없으면 (아직 장마감 전) stock_open 반환
    current_price = prediction.actual_close if prediction.actual_close else prediction.stock_open

    return StockPriceResponse(
        stock_code=stock_code,
        open_price=int(prediction.stock_open),
        current_price=int(current_price),
        is_market_open=False,
    )
