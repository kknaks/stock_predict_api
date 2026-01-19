"""
실시간 가격 SSE 엔드포인트
"""

import asyncio
import json
import logging
from typing import Set

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.price_cache import get_price_cache

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
            # 초기 가격 전송
            for stock_code in subscribed_stocks:
                cached_price = price_cache.get(stock_code)
                if cached_price:
                    yield format_sse_event("price_update", {
                        "stock_code": stock_code,
                        "current_price": cached_price.current_price,
                        "timestamp": cached_price.timestamp.isoformat(),
                    })
            
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
                        
                        # 가격이 변경되었거나 처음이면 전송
                        if last_price != current_price or stock_code not in last_prices:
                            last_prices[stock_code] = current_price
                            yield format_sse_event("price_update", {
                                "stock_code": stock_code,
                                "current_price": current_price,
                                "timestamp": cached_price.timestamp.isoformat(),
                            })
                
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
