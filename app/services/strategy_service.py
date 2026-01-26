import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.strategy_repository import StrategyRepository
from app.repositories.account_repository import AccountRepository
from app.schemas.td_position import (
    TdPositionResponse,
    AccountPositionResponse,
    TdPositionSummary,
    StockPosition,
    PositionStatus,
)
from app.schemas.users import CreateStrategyRequest, UpdateStrategyRequest
from app.database.database.strategy import StrategyStatus, UserStrategy
from app.services.price_cache import get_price_cache

logger = logging.getLogger(__name__)


class StrategyService:
    """전략/포지션 관련 비즈니스 로직"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = StrategyRepository(db)
        self.account_repo = AccountRepository(db)

    async def get_td_position(self, user_id: int, date_str: str) -> TdPositionResponse:
        """
        당일 포지션 조회 (사용자의 모든 계좌)

        Args:
            user_id: 사용자 ID
            date_str: 조회 날짜 (YYYY-MM-DD)

        Returns:
            TdPositionResponse (계좌별 포지션)
        """
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # 1. 사용자의 모든 계좌 조회
        accounts = await self.account_repo.get_by_user_uid(user_id)

        account_positions = []
        for account in accounts:
            position = await self._get_account_position(account, target_date, date_str)
            account_positions.append(position)

        return TdPositionResponse(
            date=date_str,
            accounts=account_positions,
        )

    async def _get_account_position(
        self,
        account,
        target_date,
        date_str: str
    ) -> AccountPositionResponse:
        """개별 계좌의 포지션 조회"""
        # DB에서 DailyStrategy 및 종목 정보 조회
        daily_strategy, stocks = await self.repo.get_td_position(account.id, target_date)

        # 데이터 없는 경우 빈 응답
        if not daily_strategy:
            return AccountPositionResponse(
                account_id=account.id,
                account_number=account.account_number,
                account_name=account.account_name or "",
                daily_strategy_id=None,
                summary=TdPositionSummary(),
                positions=[],
                updated_at=None,
            )

        # 2. 종목별 포지션 정보 변환
        positions = []
        price_cache = get_price_cache()

        # 실현손익 (매도 완료)
        realized_profit_amount = 0.0

        # 미실현 (보유 중)
        holding_buy_amount = 0.0
        holding_eval_amount = 0.0

        # 카운트
        not_purchased_count = 0
        holding_count = 0
        sold_count = 0
        target_reached_count = 0
        stop_loss_count = 0

        for stock in stocks:
            # 매수/매도 금액 계산
            buy_amount = None
            if stock.buy_price and stock.buy_quantity:
                buy_amount = stock.buy_price * stock.buy_quantity

            sell_amount = None
            if stock.sell_price and stock.sell_quantity:
                sell_amount = stock.sell_price * stock.sell_quantity

            # 보유수량 계산
            buy_qty = int(stock.buy_quantity or 0)
            sell_qty = int(stock.sell_quantity or 0)
            holding_quantity = buy_qty - sell_qty

            # 수익금액 계산 (매도 완료된 경우만)
            profit_amount = None
            if buy_amount and sell_amount:
                profit_amount = sell_amount - buy_amount

            # 포지션 상태 결정
            status = self._determine_position_status(
                stock=stock,
                holding_quantity=holding_quantity,
            )

            # 현재가 조회 (보유 중인 종목)
            current_price = None
            eval_amount = None
            price_data = price_cache.get(stock.stock_code)
            if price_data:
                current_price = int(price_data.current_price)
                if holding_quantity > 0:
                    eval_amount = current_price * holding_quantity
            # TODO: PriceCache에 없으면 DB에서 종가(close_price) 조회하는 로직 추가

            # 상태별 집계
            if status == PositionStatus.NOT_PURCHASED:
                not_purchased_count += 1
            elif status == PositionStatus.HOLDING:
                holding_count += 1
                # 보유 중인 종목의 매입금액
                if buy_amount:
                    holding_buy_amount += buy_amount
                # 보유 중인 종목의 평가금액
                if eval_amount:
                    holding_eval_amount += eval_amount
            else:
                # 매도 완료된 종목의 실현손익
                if profit_amount:
                    realized_profit_amount += profit_amount

                if status == PositionStatus.SOLD:
                    sold_count += 1
                elif status == PositionStatus.TARGET_REACHED:
                    target_reached_count += 1
                    sold_count += 1
                elif status == PositionStatus.STOP_LOSS:
                    stop_loss_count += 1
                    sold_count += 1

            # 주문 정보
            order_count = len(stock.orders) if stock.orders else 0
            last_order_at = None
            if stock.orders:
                last_order_at = max(o.ordered_at for o in stock.orders)

            position = StockPosition(
                stock_code=stock.stock_code,
                stock_name=stock.stock_name,
                buy_price=stock.buy_price,
                buy_quantity=buy_qty if buy_qty > 0 else None,
                buy_amount=buy_amount,
                sell_price=stock.sell_price,
                sell_quantity=sell_qty if sell_qty > 0 else None,
                sell_amount=sell_amount,
                holding_quantity=holding_quantity,
                current_price=current_price,
                eval_amount=eval_amount,
                target_price=stock.target_sell_price,
                stop_loss_price=stock.stop_loss_price,
                profit_rate=stock.profit_rate,
                profit_amount=profit_amount,
                status=status,
                order_count=order_count,
                last_order_at=last_order_at,
            )
            positions.append(position)

        # 3. 요약 정보 계산
        holding_profit_amount = holding_eval_amount - holding_buy_amount
        holding_profit_rate = 0.0
        if holding_buy_amount > 0:
            holding_profit_rate = (holding_profit_amount / holding_buy_amount) * 100

        summary = TdPositionSummary(
            realized_profit_amount=realized_profit_amount,
            holding_buy_amount=holding_buy_amount,
            holding_eval_amount=holding_eval_amount,
            holding_profit_amount=holding_profit_amount,
            holding_profit_rate=round(holding_profit_rate, 2),
            total_holding_count=holding_count,
            total_sold_count=sold_count,
            total_target_reached_count=target_reached_count,
            total_stop_loss_count=stop_loss_count,
        )

        return AccountPositionResponse(
            account_id=account.id,
            account_number=account.account_number,
            account_name=account.account_name or "",
            daily_strategy_id=daily_strategy.id,
            summary=summary,
            positions=positions,
            updated_at=daily_strategy.updated_at,
        )

    def _determine_position_status(
        self,
        stock,
        holding_quantity: int,
    ) -> PositionStatus:
        """
        포지션 상태 결정

        - 매수 실패: 매수하지 못한 경우 (buy_price가 None이거나 buy_quantity가 0)
        - 보유 중: 매도 안 함
        - 목표가 도달: 매도가 >= 목표가
        - 손절: 매도가 <= 손절가
        - 매도 완료: 그 외 매도 완료
        """
        # 매수하지 못한 경우 (buy_price가 None이거나 buy_quantity가 0)
        if not stock.buy_price or not stock.buy_quantity or stock.buy_quantity == 0:
            return PositionStatus.NOT_PURCHASED

        # 보유 중인 경우
        if holding_quantity > 0:
            return PositionStatus.HOLDING

        # 매도 완료 시 상태 판별 (holding_quantity가 0이고 sell_price가 있는 경우)
        if not stock.sell_price:
            return PositionStatus.HOLDING  # 매도가 없으면 아직 보유 중으로 간주
        
        buy_price = stock.buy_price
        sell_price = stock.sell_price
        target_price = stock.target_sell_price
        stop_loss_price = stock.stop_loss_price

        # 목표가 도달 여부
        if target_price and sell_price >= buy_price:
            return PositionStatus.TARGET_REACHED

        # 손절 여부
        if stop_loss_price and sell_price <= stop_loss_price:
            return PositionStatus.STOP_LOSS

        # 일반 매도
        return PositionStatus.SOLD

    async def update_strategy(
        self,
        strategy_id: int,
        account_id: int,
        request: UpdateStrategyRequest
    ) -> Optional[UserStrategy]:
        """
        전략 업데이트

        Args:
            strategy_id: UserStrategy ID
            account_id: 계좌 ID
            request: 업데이트 요청

        Returns:
            업데이트된 UserStrategy 또는 None
        """
        # 요청 데이터를 딕셔너리로 변환 (None이 아닌 값만)
        update_data = {}

        if request.investment_weight is not None:
            update_data["investment_weight"] = request.investment_weight
        if request.ls_ratio is not None:
            update_data["ls_ratio"] = request.ls_ratio
        if request.tp_ratio is not None:
            update_data["tp_ratio"] = request.tp_ratio
        if request.is_auto is not None:
            update_data["is_auto"] = request.is_auto
        if request.status is not None:
            update_data["status"] = request.status
        if request.strategy_weight_type_id is not None:
            update_data["weight_type_id"] = request.strategy_weight_type_id

        # ACTIVE로 변경하려는 경우, 다른 전략들을 INACTIVE로 변경
        if request.status == StrategyStatus.ACTIVE:
            await self.repo.deactivate_other_strategies(account_id, strategy_id)

        return await self.repo.update_user_strategy(strategy_id, account_id, update_data)

    async def delete_strategy(self, strategy_id: int, account_id: int) -> bool:
        """
        전략 삭제 (소프트 삭제)

        Args:
            strategy_id: UserStrategy ID
            account_id: 계좌 ID

        Returns:
            성공 여부
        """
        return await self.repo.soft_delete_user_strategy(strategy_id, account_id)

    async def get_all_strategy_info(self):
        """전략 정보 목록 조회"""
        return await self.repo.get_all_strategy_info()

    async def get_all_strategy_weight_types(self):
        """가중치 타입 목록 조회"""
        return await self.repo.get_all_strategy_weight_types()

    async def create_strategy(
        self,
        account_id: int,
        request: CreateStrategyRequest
    ) -> UserStrategy:
        """
        전략 생성

        Args:
            account_id: 계좌 ID
            request: 생성 요청

        Returns:
            생성된 UserStrategy
        """
        return await self.repo.create_user_strategy(
            account_id=account_id,
            strategy_id=request.strategy_id,
            investment_weight=request.investment_weight,
            ls_ratio=request.ls_ratio,
            tp_ratio=request.tp_ratio,
            is_auto=request.is_auto,
            weight_type_id=request.strategy_weight_type_id,
        )
