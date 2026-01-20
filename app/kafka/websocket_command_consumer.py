"""
Kafka Consumer for WebSocket Commands

웹소켓 명령 (STOP 등)을 Kafka에서 수신하는 Consumer
"""

import asyncio
import json
import logging
from typing import Callable, Optional, List, Any

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError

from app.config.kafka_connections import get_kafka_config

logger = logging.getLogger(__name__)


class WebSocketCommandMessage:
    """웹소켓 명령 메시지"""

    def __init__(self, command: str, timestamp: str, target: str, **kwargs):
        self.command = command
        self.timestamp = timestamp
        self.target = target
        self.extra = kwargs

    def __repr__(self) -> str:
        return f"<WebSocketCommandMessage(command={self.command}, target={self.target})>"


class KafkaWebSocketCommandConsumer:
    """웹소켓 명령을 수신하는 Kafka Consumer"""

    def __init__(self):
        self._config = get_kafka_config()
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
        self._handlers: List[Callable[[WebSocketCommandMessage], Any]] = []

    def add_handler(self, handler: Callable[[WebSocketCommandMessage], Any]) -> None:
        """메시지 수신 시 호출될 핸들러 등록"""
        self._handlers.append(handler)
        logger.info(f"WebSocket command handler registered: {handler.__name__}")

    async def start(self) -> bool:
        """Consumer 시작 및 연결 확인"""
        try:
            self._consumer = AIOKafkaConsumer(
                self._config.topic_websocket_commands,
                bootstrap_servers=self._config.bootstrap_servers_list,
                group_id=f"{self._config.kafka_group_id}-websocket-cmd",
                auto_offset_reset=self._config.kafka_auto_offset_reset,
                enable_auto_commit=self._config.kafka_enable_auto_commit,
                value_deserializer=lambda m: m.decode('utf-8'),
            )

            await self._consumer.start()
            self._running = True
            logger.info(
                f"WebSocket command Kafka consumer started. "
                f"Topic: {self._config.topic_websocket_commands}, "
                f"Servers: {self._config.bootstrap_servers}"
            )
            return True

        except KafkaConnectionError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error starting websocket command consumer: {e}", exc_info=True)
            return False

    async def stop(self) -> None:
        """Consumer 중지"""
        self._running = False
        if self._consumer:
            await self._consumer.stop()
            logger.info("WebSocket command Kafka consumer stopped")

    async def consume(self) -> None:
        """메시지 수신 루프"""
        if not self._consumer:
            logger.error("WebSocket command consumer not started")
            return

        logger.info("Starting websocket command message consumption loop...")

        try:
            async for msg in self._consumer:
                if not self._running:
                    break

                try:
                    # JSON 파싱
                    data = json.loads(msg.value)
                    command_msg = WebSocketCommandMessage(**data)

                    logger.info(
                        f"Received websocket command: "
                        f"command={command_msg.command}, "
                        f"target={command_msg.target}, "
                        f"timestamp={command_msg.timestamp}"
                    )

                    # 등록된 핸들러들 호출
                    for handler in self._handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(command_msg)
                            else:
                                handler(command_msg)
                        except Exception as e:
                            logger.error(f"WebSocket command handler error: {e}", exc_info=True)

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"WebSocket command message processing error: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"WebSocket command consumer loop error: {e}", exc_info=True)
        finally:
            logger.info("WebSocket command message consumption loop ended")


# 싱글톤 인스턴스
_consumer_instance: Optional[KafkaWebSocketCommandConsumer] = None


def get_websocket_command_consumer() -> KafkaWebSocketCommandConsumer:
    """WebSocket Command Kafka Consumer 싱글톤 인스턴스 반환"""
    global _consumer_instance
    if _consumer_instance is None:
        _consumer_instance = KafkaWebSocketCommandConsumer()
    return _consumer_instance
