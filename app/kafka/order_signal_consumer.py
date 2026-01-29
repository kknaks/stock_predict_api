import asyncio
import json
import logging
from typing import Callable, Optional, List

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from app.config.kafka_connections import get_kafka_config
from app.schemas.order_signal import OrderSignalMessage, OrderResultMessage

logger = logging.getLogger(__name__)

class KafkaOrderSignalConsumer:
    """주문 시그널 및 주문 결과 메시지를 Kafka에서 수신하는 Consumer"""
    
    def __init__(self):
        self._config = get_kafka_config()
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._handlers: List[Callable[[OrderSignalMessage], None]] = []
        self._order_result_handlers: List[Callable[[OrderResultMessage], None]] = []

    def add_handler(self, handler: Callable[[OrderSignalMessage], None]) -> None:
        """주문 시그널 메시지 핸들러 등록"""
        self._handlers.append(handler)
        logger.info(f"Order signal handler registered: {handler.__name__}")

    def add_order_result_handler(self, handler: Callable[[OrderResultMessage], None]) -> None:
        """주문 결과 메시지 핸들러 등록"""
        self._order_result_handlers.append(handler)
        logger.info(f"Order result handler registered: {handler.__name__}")

    async def start(self) -> bool:
        """Consumer 시작 및 연결 확인"""
        try:
            self._consumer = AIOKafkaConsumer(
                self._config.topic_order_signal,
                bootstrap_servers=self._config.bootstrap_servers_list,
                group_id=f"{self._config.kafka_group_id}-order-signal",
                auto_offset_reset=self._config.kafka_auto_offset_reset,
                enable_auto_commit=self._config.kafka_enable_auto_commit,
                value_deserializer=lambda m: m.decode('utf-8'),
            )
            await self._consumer.start()
            self._running = True
            logger.info(
                f"Order signal Kafka consumer started. "
                f"Topic: {self._config.topic_order_signal}, "
                f"Servers: {self._config.bootstrap_servers}"
            )
            return True
        except KafkaConnectionError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting daily strategy consumer: {e}", exc_info=True)
            return False

    async def stop(self) -> None:
        """Consumer 중지"""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            logger.info("Daily strategy Kafka consumer stopped")

    async def consume(self) -> None:
        """메시지 수신 루프"""
        if not self._consumer:
            logger.error("Order signal consumer not started")
            return

        logger.info("Starting order signal message consumption loop...")

        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                try:
                    # JSON 파싱
                    data = json.loads(msg.value)
                    
                    # 메시지 타입 구분 (order_no가 있으면 OrderResultMessage)
                    if "order_no" in data:
                        # 주문 결과 메시지 (주문 접수 또는 체결통보)
                        try:
                            order_result_msg = OrderResultMessage(**data)
                            logger.info(
                                f"Received order result message: order_no={order_result_msg.order_no}, "
                                f"status={order_result_msg.status}, "
                                f"user_strategy_id={order_result_msg.user_strategy_id}"
                            )

                            # 등록된 주문 결과 핸들러들 호출
                            for handler in self._order_result_handlers:
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(order_result_msg)
                                else:
                                    handler(order_result_msg)
                        except Exception as e:
                            logger.error(f"Order result handler error: {e}, data={data}", exc_info=True)
                    else:
                        # 기존 주문 시그널 메시지 (하위 호환성)
                        try:
                            order_signal_msg = OrderSignalMessage(**data)
                            logger.info(
                                f"Received order signal message: {order_signal_msg.user_strategy_id} "
                                f"at {order_signal_msg.timestamp}"
                            )

                            # 등록된 주문 시그널 핸들러들 호출
                            for handler in self._handlers:
                                try:
                                    if asyncio.iscoroutinefunction(handler):
                                        await handler(order_signal_msg)
                                    else:
                                        handler(order_signal_msg)
                                except Exception as e:
                                    logger.error(f"Handler error: {e}", exc_info=True)
                        except Exception as e:
                            logger.error(f"Failed to parse OrderSignalMessage: {e}, data={data}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Message processing error: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Consumer loop error: {e}", exc_info=True)
        finally:
            logger.info("Order signal message consumption loop ended")

    async def check_connection(self) -> bool:
        """Kafka 연결 상태 확인"""
        if not self._consumer:
            return False

        try:
            # 메타데이터 요청으로 연결 확인
            await self._consumer.topics()
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False

            
_consumer_instance: Optional[KafkaOrderSignalConsumer] = None


def get_order_signal_consumer() -> KafkaOrderSignalConsumer:
    """Order Signal Kafka Consumer 싱글톤 인스턴스 반환"""
    global _consumer_instance
    if _consumer_instance is None:
        _consumer_instance = KafkaOrderSignalConsumer()
    return _consumer_instance