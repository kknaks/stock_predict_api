"""
Kafka order_signal 토픽 메시지 파싱 테스트
"""
import pytest
from datetime import datetime
from app.schemas.order_signal import OrderResultMessage, PositionInfo


class TestOrderResultMessage:
    """OrderResultMessage 파싱 테스트"""

    def test_mock_order_executed(self):
        """1. Mock 주문/체결 (즉시 체결) - stock_code 없음"""
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": 123,
            "daily_strategy_id": 1,
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",  # Mock에서도 stock_code 필요
            "order_no": "MOCK-20260124090100-A1B2C3D4",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "MOCK",
            "is_mock": True,
            "status": "executed",
            "executed_quantity": 10,
            "executed_price": 75000,
            "total_executed_quantity": 10,
            "total_executed_price": 75000,
            "remaining_quantity": 0,
            "is_fully_executed": True,
            "position": {
                "holding_quantity": 10,
                "average_price": 75000,
                "total_buy_quantity": 10,
                "total_sell_quantity": 0,
                "realized_pnl": 0.0
            }
        }

        msg = OrderResultMessage(**data)

        assert msg.user_strategy_id == 123
        assert msg.daily_strategy_id == 1
        assert msg.stock_name == "삼성전자"
        assert msg.order_type == "BUY"
        assert msg.order_no == "MOCK-20260124090100-A1B2C3D4"
        assert msg.is_mock is True
        assert msg.status == "executed"
        assert msg.is_fully_executed is True
        assert msg.position is not None
        assert msg.position.holding_quantity == 10
        assert msg.position.average_price == 75000
        assert msg.position.realized_pnl == 0.0

    def test_mock_order_without_stock_code_should_fail(self):
        """Mock 메시지에 stock_code가 없으면 실패해야 함 (현재 스키마 기준)"""
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": 123,
            "daily_strategy_id": 1,
            "stock_name": "삼성전자",
            "order_type": "BUY",
            # stock_code 없음
            "order_no": "MOCK-20260124090100-A1B2C3D4",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "MOCK",
            "is_mock": True,
            "status": "executed",
            "executed_quantity": 10,
            "executed_price": 75000,
            "total_executed_quantity": 10,
            "total_executed_price": 75000,
            "remaining_quantity": 0,
            "is_fully_executed": True,
            "position": {
                "holding_quantity": 10,
                "average_price": 75000,
                "total_buy_quantity": 10,
                "total_sell_quantity": 0,
                "realized_pnl": 0.0
            }
        }

        # stock_code가 필수이므로 ValidationError 발생
        with pytest.raises(Exception):
            OrderResultMessage(**data)

    def test_paper_real_order_received(self):
        """2. Paper/Real 주문 접수"""
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": 123,
            "daily_strategy_id": 1,
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "ordered",
            "executed_quantity": 0,
            "executed_price": 0.0,
            "total_executed_quantity": 0,
            "total_executed_price": 0.0,
            "remaining_quantity": 10,
            "is_fully_executed": False,
            "position": None
        }

        msg = OrderResultMessage(**data)

        assert msg.user_strategy_id == 123
        assert msg.stock_code == "005930"
        assert msg.order_no == "0001234567"
        assert msg.is_mock is False
        assert msg.status == "ordered"
        assert msg.executed_quantity == 0
        assert msg.is_fully_executed is False
        assert msg.position is None

    def test_paper_real_fully_executed(self):
        """3. Paper/Real 체결 (전량)"""
        data = {
            "timestamp": "2026-01-24T09:01:05.654321",
            "user_strategy_id": 123,
            "daily_strategy_id": 1,
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "executed",
            "executed_quantity": 10,
            "executed_price": 75100,
            "total_executed_quantity": 10,
            "total_executed_price": 75100,
            "remaining_quantity": 0,
            "is_fully_executed": True,
            "position": {
                "holding_quantity": 10,
                "average_price": 75100,
                "total_buy_quantity": 10,
                "total_sell_quantity": 0,
                "realized_pnl": 0.0
            }
        }

        msg = OrderResultMessage(**data)

        assert msg.status == "executed"
        assert msg.executed_quantity == 10
        assert msg.executed_price == 75100
        assert msg.is_fully_executed is True
        assert msg.remaining_quantity == 0
        assert msg.position is not None
        assert msg.position.holding_quantity == 10
        assert msg.position.average_price == 75100

    def test_paper_real_partially_executed(self):
        """4. Paper/Real 부분 체결"""
        data = {
            "timestamp": "2026-01-24T09:01:03.111111",
            "user_strategy_id": 123,
            "daily_strategy_id": 1,
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": 100,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "partially_executed",
            "executed_quantity": 30,
            "executed_price": 75000,
            "total_executed_quantity": 30,
            "total_executed_price": 75000,
            "remaining_quantity": 70,
            "is_fully_executed": False,
            "position": {
                "holding_quantity": 30,
                "average_price": 75000,
                "total_buy_quantity": 30,
                "total_sell_quantity": 0,
                "realized_pnl": 0.0
            }
        }

        msg = OrderResultMessage(**data)

        assert msg.status == "partially_executed"
        assert msg.order_quantity == 100
        assert msg.executed_quantity == 30
        assert msg.total_executed_quantity == 30
        assert msg.remaining_quantity == 70
        assert msg.is_fully_executed is False
        assert msg.position is not None
        assert msg.position.holding_quantity == 30

    def test_sell_order_with_pnl(self):
        """5. 매도 체결 (손익 발생)"""
        data = {
            "timestamp": "2026-01-24T14:30:00.123456",
            "user_strategy_id": 123,
            "daily_strategy_id": 1,
            "stock_name": "삼성전자",
            "order_type": "SELL",
            "stock_code": "005930",
            "order_no": "0001234999",
            "order_quantity": 10,
            "order_price": 76500,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "executed",
            "executed_quantity": 10,
            "executed_price": 76500,
            "total_executed_quantity": 10,
            "total_executed_price": 76500,
            "remaining_quantity": 0,
            "is_fully_executed": True,
            "position": {
                "holding_quantity": 0,
                "average_price": 75100,
                "total_buy_quantity": 10,
                "total_sell_quantity": 10,
                "realized_pnl": 14000.0
            }
        }

        msg = OrderResultMessage(**data)

        assert msg.order_type == "SELL"
        assert msg.status == "executed"
        assert msg.executed_price == 76500
        assert msg.is_fully_executed is True
        assert msg.position is not None
        assert msg.position.holding_quantity == 0
        assert msg.position.total_sell_quantity == 10
        assert msg.position.realized_pnl == 14000.0

    def test_string_number_parsing(self):
        """문자열로 된 숫자 파싱 테스트"""
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": "123",  # 문자열
            "daily_strategy_id": "1",  # 문자열
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": "10",  # 문자열
            "order_price": "75000.0",  # 문자열
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "ordered",
            "executed_quantity": "0",  # 문자열
            "executed_price": "0.0",  # 문자열
            "total_executed_quantity": "0",  # 문자열
            "total_executed_price": "0.0",  # 문자열
            "remaining_quantity": "10",  # 문자열
            "is_fully_executed": False,
            "position": None
        }

        msg = OrderResultMessage(**data)

        assert msg.user_strategy_id == 123
        assert msg.daily_strategy_id == 1
        assert msg.order_quantity == 10
        assert msg.order_price == 75000.0
        assert msg.executed_quantity == 0
        assert msg.remaining_quantity == 10


class TestPositionInfo:
    """PositionInfo 파싱 테스트"""

    def test_position_info_defaults(self):
        """기본값으로 PositionInfo 생성"""
        pos = PositionInfo()

        assert pos.holding_quantity == 0
        assert pos.average_price == 0.0
        assert pos.total_buy_quantity == 0
        assert pos.total_sell_quantity == 0
        assert pos.realized_pnl == 0.0

    def test_position_info_with_values(self):
        """값이 있는 PositionInfo 생성"""
        pos = PositionInfo(
            holding_quantity=100,
            average_price=50000.5,
            total_buy_quantity=150,
            total_sell_quantity=50,
            realized_pnl=25000.0
        )

        assert pos.holding_quantity == 100
        assert pos.average_price == 50000.5
        assert pos.total_buy_quantity == 150
        assert pos.total_sell_quantity == 50
        assert pos.realized_pnl == 25000.0


class TestOrderResultMessageEdgeCases:
    """OrderResultMessage 엣지 케이스 테스트"""

    def test_optional_daily_strategy_id_none(self):
        """daily_strategy_id가 None인 경우"""
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": 123,
            "daily_strategy_id": None,
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "ordered",
            "executed_quantity": 0,
            "executed_price": 0.0,
            "total_executed_quantity": 0,
            "total_executed_price": 0.0,
            "remaining_quantity": 10,
            "is_fully_executed": False,
            "position": None
        }

        msg = OrderResultMessage(**data)
        assert msg.daily_strategy_id is None

    def test_optional_daily_strategy_id_missing(self):
        """daily_strategy_id가 없는 경우"""
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": 123,
            # daily_strategy_id 없음
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "ordered",
            "executed_quantity": 0,
            "executed_price": 0.0,
            "total_executed_quantity": 0,
            "total_executed_price": 0.0,
            "remaining_quantity": 10,
            "is_fully_executed": False,
            "position": None
        }

        msg = OrderResultMessage(**data)
        assert msg.daily_strategy_id is None

    def test_empty_stock_name(self):
        """stock_name이 빈 문자열인 경우"""
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": 123,
            "daily_strategy_id": 1,
            "stock_name": "",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "ordered",
            "executed_quantity": 0,
            "executed_price": 0.0,
            "total_executed_quantity": 0,
            "total_executed_price": 0.0,
            "remaining_quantity": 10,
            "is_fully_executed": False,
            "position": None
        }

        msg = OrderResultMessage(**data)
        assert msg.stock_name == ""

    def test_timestamp_parsing(self):
        """다양한 timestamp 형식 파싱"""
        # ISO 형식 with microseconds
        data = {
            "timestamp": "2026-01-24T09:01:00.123456",
            "user_strategy_id": 123,
            "stock_name": "삼성전자",
            "order_type": "BUY",
            "stock_code": "005930",
            "order_no": "0001234567",
            "order_quantity": 10,
            "order_price": 75000,
            "order_dvsn": "00",
            "account_no": "50123456-01",
            "is_mock": False,
            "status": "ordered",
            "executed_quantity": 0,
            "executed_price": 0.0,
            "total_executed_quantity": 0,
            "total_executed_price": 0.0,
            "remaining_quantity": 10,
            "is_fully_executed": False,
            "position": None
        }

        msg = OrderResultMessage(**data)
        assert isinstance(msg.timestamp, datetime)
        assert msg.timestamp.year == 2026
        assert msg.timestamp.month == 1
        assert msg.timestamp.day == 24


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
