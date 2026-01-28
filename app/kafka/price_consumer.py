"""
Kafka Consumer for Real-time Price Data

실시간 가격 데이터를 Kafka에서 수신하는 Consumer
"""

import asyncio
import json
import logging
from typing import Callable, Optional, List

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from app.config.kafka_connections import get_kafka_config
from app.schemas.price import PriceMessage

logger = logging.getLogger(__name__)


class KafkaPriceConsumer:
    """실시간 가격 데이터를 수신하는 Kafka Consumer"""

    def __init__(self):
        self._config = get_kafka_config()
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._handlers: List[Callable[[PriceMessage], None]] = []

    def add_handler(self, handler: Callable[[PriceMessage], None]) -> None:
        """메시지 수신 시 호출될 핸들러 등록"""
        self._handlers.append(handler)
        logger.info(f"Price handler registered: {handler.__name__}")

    async def start(self) -> bool:
        """Consumer 시작 및 연결 확인"""
        try:
            self._consumer = AIOKafkaConsumer(
                self._config.topic_price,
                bootstrap_servers=self._config.bootstrap_servers_list,
                group_id=f"{self._config.kafka_group_id}-price",
                auto_offset_reset=self._config.kafka_auto_offset_reset,
                enable_auto_commit=self._config.kafka_enable_auto_commit,
                value_deserializer=lambda m: m.decode('utf-8'),
            )

            await self._consumer.start()
            self._running = True
            logger.info(
                f"Price Kafka consumer started. "
                f"Topic: {self._config.topic_price}, "
                f"Servers: {self._config.bootstrap_servers}"
            )
            return True

        except KafkaConnectionError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting price consumer: {e}", exc_info=True)
            return False

    async def stop(self) -> None:
        """Consumer 중지"""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            logger.info("Price Kafka consumer stopped")

    async def consume(self) -> None:
        """메시지 수신 루프"""
        if not self._consumer:
            logger.error("Price consumer not started")
            return

        logger.info("Starting price message consumption loop...")

        try:
            async for msg in self._consumer:
                if not self._running:
                    break

                try:
                    # JSON 파싱
                    data = json.loads(msg.value)
                    price_msg = PriceMessage(**data)

                    # logger.debug(
                    #     f"Received price data: "
                    #     f"stock_code={price_msg.stock_code}, "
                    #     f"current_price={price_msg.current_price}, "
                    #     f"timestamp={price_msg.timestamp}"
                    # )

                    # 등록된 핸들러들 호출
                    for handler in self._handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(price_msg)
                            else:
                                handler(price_msg)
                        except Exception as e:
                            logger.error(f"Price handler error: {e}", exc_info=True)

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Price message processing error: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Price consumer loop error: {e}", exc_info=True)
        finally:
            logger.info("Price message consumption loop ended")

    async def check_connection(self) -> bool:
        """Kafka 연결 상태 확인"""
        if not self._consumer:
            return False

        try:
            # 메타데이터 요청으로 연결 확인
            await self._consumer.topics()
            return True
        except Exception as e:
            logger.error(f"Price consumer connection check failed: {e}")
            return False


# 싱글톤 인스턴스
_consumer_instance: Optional[KafkaPriceConsumer] = None


def get_price_consumer() -> KafkaPriceConsumer:
    """Price Kafka Consumer 싱글톤 인스턴스 반환"""
    global _consumer_instance
    if _consumer_instance is None:
        _consumer_instance = KafkaPriceConsumer()
    return _consumer_instance
