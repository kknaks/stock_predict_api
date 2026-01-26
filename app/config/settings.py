"""
FastAPI 서버 설정

Pydantic Settings를 사용하여 .env 파일에서 설정 로드
"""

from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """API 서버 설정"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # -------------------------------------------
    # API Server
    # -------------------------------------------
    app_name: str = "Stock Predict API"
    app_version: str = "0.1.0"
    debug: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # -------------------------------------------
    # Database (PostgreSQL)
    # -------------------------------------------
    db_host: str = "stock-predict-db"
    db_port: int = 5432
    db_name: str = "stock_predict"
    db_user: str = "postgres"
    db_password: str = ""
    db_echo: bool = False
    
    # Docker 네트워크 사용 여부
    db_use_docker_network: bool = False
    db_docker_host: str = "stock-predict-db"
    
    @property
    def effective_db_host(self) -> str:
        """실제 사용할 DB 호스트 (Docker 네트워크 사용 시 docker_host 사용)"""
        return self.db_docker_host if self.db_use_docker_network else self.db_host
    
    # -------------------------------------------
    # Kafka / Redpanda
    # -------------------------------------------
    kafka_bootstrap_servers: str = "localhost:19092"
    kafka_bootstrap_servers_internal: str = "redpanda-0:9092,redpanda-1:9092,redpanda-2:9092"
    kafka_use_internal: bool = False

    kafka_group_id: str = "websocket-server-group"
    kafka_auto_offset_reset: str = "latest"
    kafka_enable_auto_commit: bool = True

    daily_strategy: str = "daily_strategy"
    order_signal: str = "order_signal"
    topic_price: str = "stock_price"
    topic_websocket_commands: str = "kis_websocket_commands"
    topic_asking_price: str = "asking_price"
    topic_manual_sell_signal: str = "manual-sell-signal"
    
    @property
    def kafka_servers(self) -> str:
        """Kafka 브로커 주소 (내부/외부 선택)"""
        return self.kafka_bootstrap_servers_internal if self.kafka_use_internal else self.kafka_bootstrap_servers
    
    @property
    def kafka_servers_list(self) -> List[str]:
        """Kafka 브로커 주소 리스트"""
        return [s.strip() for s in self.kafka_servers.split(',')]

    # -------------------------------------------
    # JWT Authentication
    # -------------------------------------------
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # -------------------------------------------
    # Master Account
    # -------------------------------------------
    master_secret_key: str = "master-secret-key-change-this"  # 마스터 계정 생성용 시크릿
    
    # -------------------------------------------
    # CORS
    # -------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    @property
    def database_url(self) -> str:
        """SQLAlchemy 동기 연결 URL"""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.effective_db_host}:{self.db_port}/{self.db_name}"
    
    @property
    def async_database_url(self) -> str:
        """SQLAlchemy 비동기 연결 URL (asyncpg)"""
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.effective_db_host}:{self.db_port}/{self.db_name}"


@lru_cache()
def get_settings() -> Settings:
    """
    설정 싱글톤 인스턴스 반환 (캐싱)
    
    Returns:
        Settings 인스턴스
    """
    return Settings()


# 편의를 위한 전역 인스턴스
settings = get_settings()
