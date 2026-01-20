"""
Stock Predict API - FastAPI Application
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, init_db, close_db
from app.kafka.daily_strategy_consumer import get_daily_strategy_consumer
from app.kafka.order_signal_consumer import get_order_signal_consumer
from app.kafka.price_consumer import get_price_consumer
from app.kafka.websocket_command_consumer import get_websocket_command_consumer
from app.handler.price_handler import get_price_handler
from app.services.price_cache import get_price_cache
from app.handler.daily_strategy_handler import get_daily_strategy_handler
from app.handler.order_signal_hanlder import get_order_signal_handler
from app.handler.order_result_handler import get_order_result_handler
from app.handler.candle_handler import get_candle_handler

# 로깅 설정
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# aiokafka의 DEBUG 로그를 줄이기 위해 INFO 레벨로 설정
logging.getLogger("aiokafka").setLevel(logging.INFO)

# 백그라운드 태스크
_consumer_task: Optional[asyncio.Task] = None
_order_consumer_task: Optional[asyncio.Task] = None
_price_consumer_task: Optional[asyncio.Task] = None
_websocket_cmd_consumer_task: Optional[asyncio.Task] = None
_consumer_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행되는 lifespan 이벤트"""
    global _consumer_task, _order_consumer_task, _price_consumer_task, _websocket_cmd_consumer_task, _consumer_tasks
    
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    await init_db()
    
    # Daily Strategy Kafka Consumer 시작
    daily_strategy_consumer = get_daily_strategy_consumer()
    daily_strategy_handler = get_daily_strategy_handler()

    # Order Signal Kafka Consumer 시작
    order_signal_consumer = get_order_signal_consumer()
    order_signal_handler = get_order_signal_handler()
    order_result_handler = get_order_result_handler()
    
    # Price Kafka Consumer 시작
    price_consumer = get_price_consumer()
    price_handler = get_price_handler()
    price_cache = get_price_cache()
    
    # Price Cache 시작
    await price_cache.start()
    
    # 핸들러 등록
    daily_strategy_consumer.add_handler(daily_strategy_handler.handle_daily_strategy)
    order_signal_consumer.add_handler(order_signal_handler.handle_order_signal)
    order_signal_consumer.add_order_result_handler(order_result_handler.handle_order_result)
    price_consumer.add_handler(price_handler.handle_price)
    
    # Consumer 시작
    daily_strategy_consumer_connected = await daily_strategy_consumer.start()
    if daily_strategy_consumer_connected:
        logger.info("Daily strategy Kafka consumer connection established")
        # 백그라운드 태스크로 consume 시작
        _consumer_task = asyncio.create_task(daily_strategy_consumer.consume())
        _consumer_tasks.append(_consumer_task)
    else:
        logger.warning("Failed to connect to Daily strategy Kafka consumer")
    
    order_signal_consumer_connected = await order_signal_consumer.start()
    if order_signal_consumer_connected:
        logger.info("Order signal Kafka consumer connection established")
        _order_consumer_task = asyncio.create_task(order_signal_consumer.consume())
        _consumer_tasks.append(_order_consumer_task)
    else:
        logger.warning("Failed to connect to Order signal Kafka consumer")
    
    price_consumer_connected = await price_consumer.start()
    if price_consumer_connected:
        logger.info("Price Kafka consumer connection established")
        _price_consumer_task = asyncio.create_task(price_consumer.consume())
        _consumer_tasks.append(_price_consumer_task)
    else:
        logger.warning("Failed to connect to Price Kafka consumer")

    # WebSocket Command Kafka Consumer 시작 (STOP 신호 처리)
    websocket_cmd_consumer = get_websocket_command_consumer()
    candle_handler = get_candle_handler()

    # 핸들러 등록 (STOP 신호 → 시간봉 생성 및 DB 저장)
    websocket_cmd_consumer.add_handler(candle_handler.handle_stop_command)

    websocket_cmd_consumer_connected = await websocket_cmd_consumer.start()
    if websocket_cmd_consumer_connected:
        logger.info("WebSocket command Kafka consumer connection established")
        _websocket_cmd_consumer_task = asyncio.create_task(websocket_cmd_consumer.consume())
        _consumer_tasks.append(_websocket_cmd_consumer_task)
    else:
        logger.warning("Failed to connect to WebSocket command Kafka consumer")

    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    # Consumer 정리
    for task in _consumer_tasks:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    await daily_strategy_consumer.stop()
    await order_signal_consumer.stop()
    await price_consumer.stop()
    await websocket_cmd_consumer.stop()
    
    # Price Cache 중지
    price_cache = get_price_cache()
    await price_cache.stop()
    
    await close_db()
    logger.info("Application shutdown complete")


# FastAPI 앱 생성
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="주식 예측 API 서비스",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS 미들웨어
app.add_middleware(
    CORSMiddleware,
    # allow_origins=settings.cors_origins,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================
# API Routers
# ===========================================
from app.api.v1.router import api_router

app.include_router(api_router, prefix="/api/v1")


# ===========================================
# Health Check
# ===========================================
@app.get("/", tags=["Health"])
async def root():
    """루트 엔드포인트"""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """헬스 체크 엔드포인트"""
    return {"status": "healthy"}


# ===========================================
# 개발용 직접 실행
# ===========================================
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
