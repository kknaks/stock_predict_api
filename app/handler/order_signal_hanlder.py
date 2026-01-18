import logging
from typing import Optional
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.db_connections import get_session_factory
from app.schemas.order_signal import OrderSignalMessage
from app.repositories.stock_repository import StockRepository
from app.repositories.account_repository import AccountRepository
from app.database.database.strategy import (
    DailyStrategy as DailyStrategyModel,
    DailyStrategyStock as DailyStrategyStockModel,
)

logger = logging.getLogger(__name__)

class OrderSignalHandler:
    """주문 시그널 메시지 핸들러"""

    def __init__(self):
        self._session_factory = get_session_factory()

    async def handle_order_signal(self, message: OrderSignalMessage) -> None:
        """
        주문 시그널 메시지 처리 및 데이터베이스 저장
        """
        logger.info(
            f"Processing order signal message: {message.user_strategy_id} at {message.timestamp}"
        )

        session: Optional[AsyncSession] = None
        try:
            session = self._session_factory()

            # 주문 시그널 메시지 처리
            timestamp = message.timestamp
            user_strategy_id = message.user_strategy_id
            signal_type = message.signal_type
            stock_code = message.stock_code
            current_price = message.current_price
            target_price = message.target_price
            target_quantity = message.target_quantity
            stop_loss_price = message.stop_loss_price
            recommended_order_price = message.recommended_order_price
            
            order_date = timestamp.date()

            # DailyStrategy 조회 (stocks 관계 포함) - 레포지토리 사용
            stock_repository = StockRepository(session)
            daily_strategy = await stock_repository.get_daily_strategy_with_stocks(
                user_strategy_id, order_date
            )

            if not daily_strategy:
                logger.warning(
                    f"DailyStrategy not found: user_strategy_id={user_strategy_id}, date={order_date}"
                )
                return

            # UserStrategy 조회 (user 정보 포함)
            user_strategy = await stock_repository.get_user_strategy_with_info(user_strategy_id)
            if not user_strategy:
                logger.warning(
                    f"UserStrategy not found: user_strategy_id={user_strategy_id}"
                )
                return

            # 해당 종목 찾기
            stock = None
            for s in daily_strategy.stocks:
                if s.stock_code == stock_code:
                    stock = s
                    break

            if not stock:
                logger.warning(
                    f"DailyStrategyStock not found: stock_code={stock_code}, daily_strategy_id={daily_strategy.id}"
                )
                return

            # 계좌 조회 및 잔액 업데이트
            account_repository = AccountRepository(session)
            user_accounts = await account_repository.get_by_user_uid(user_strategy.user_id)
            
            if not user_accounts:
                logger.warning(
                    f"User accounts not found: user_id={user_strategy.user_id}"
                )
                return
            
            # 첫 번째 계좌 사용 (또는 기본 계좌 선택 로직 필요)
            account = user_accounts[0]
            
            # 주문 금액 계산
            order_amount = recommended_order_price * target_quantity

            if signal_type == "SELL":
                await self._update_sell_info(
                    session, daily_strategy, stock, stock_code,
                    recommended_order_price, target_quantity,
                    account_repository, account, order_amount
                )
            elif signal_type == "BUY":
                await self._update_buy_info(
                    session, daily_strategy, stock, stock_code,
                    recommended_order_price, target_quantity,
                    account_repository, account, order_amount
                )

            await session.commit()
            logger.info(f"Successfully processed {signal_type} signal for stock_code={stock_code}")

        except Exception as e:
            logger.error(f"Error processing order signal: {e}", exc_info=True)
            if session:
                await session.rollback()
            raise
        finally:
            if session:
                await session.close()

    async def _update_sell_info(
        self,
        session: AsyncSession,
        daily_strategy: DailyStrategyModel,
        stock: DailyStrategyStockModel,
        stock_code: str,
        recommended_order_price: float,
        target_quantity: int,
        account_repository: AccountRepository,
        account,
        order_amount: float
    ) -> None:
        """매도 정보 업데이트"""

        stock.sell_price = recommended_order_price
        stock.sell_quantity = target_quantity

        # 계좌 잔액 증가 (매도 금액 입금)
        await account_repository.update_balance(account, order_amount)
        logger.info(
            f"Account balance updated: +{order_amount:.2f}, "
            f"new balance={account.account_balance:.2f}"
        )

        # 수익률 계산 (매수가가 있는 경우에만)
        if stock.buy_price and stock.buy_quantity:
            profit_rate = ((recommended_order_price - stock.buy_price) / stock.buy_price) * 100
            stock.profit_rate = profit_rate

            # 수익금액 계산
            profit_amount = (recommended_order_price - stock.buy_price) * stock.buy_quantity
            
            # DailyStrategy의 총 매도금액 업데이트
            if daily_strategy.sell_amount is None:
                daily_strategy.sell_amount = 0.0
            daily_strategy.sell_amount += recommended_order_price * stock.sell_quantity

            # DailyStrategy의 총 수익금액 업데이트
            if daily_strategy.total_profit_amount is None:
                daily_strategy.total_profit_amount = 0.0
            daily_strategy.total_profit_amount += profit_amount

            # DailyStrategy의 총 수익률 계산 (가중 평균)
            total_buy_amount = sum(
                s.buy_price * s.buy_quantity 
                for s in daily_strategy.stocks 
                if s.buy_price and s.buy_quantity
            )
            if total_buy_amount > 0:
                daily_strategy.total_profit_rate = (
                    daily_strategy.total_profit_amount / total_buy_amount
                ) * 100

            logger.info(
                f"SELL signal processed: stock_code={stock_code}, "
                f"profit_rate={profit_rate:.2f}%, profit_amount={profit_amount:.2f}"
            )
        else:
            logger.warning(
                f"SELL signal processed but buy_price/buy_quantity not set: stock_code={stock_code}"
            )
            # 매수가 정보가 없어도 매도 정보는 저장
            if daily_strategy.sell_amount is None:
                daily_strategy.sell_amount = 0.0
            daily_strategy.sell_amount += recommended_order_price * stock.sell_quantity

    async def _update_buy_info(
        self,
        session: AsyncSession,
        daily_strategy: DailyStrategyModel,
        stock: DailyStrategyStockModel,
        stock_code: str,
        recommended_order_price: float,
        target_quantity: int,
        account_repository: AccountRepository,
        account,
        order_amount: float
    ) -> None:
        """매수 정보 업데이트"""

        stock.buy_price = recommended_order_price
        stock.buy_quantity = target_quantity

        # 계좌 잔액 감소 (매수 금액 출금)
        await account_repository.update_balance(account, -order_amount)
        logger.info(
            f"Account balance updated: -{order_amount:.2f}, "
            f"new balance={account.account_balance:.2f}"
        )

        # DailyStrategy의 총 매수금액 업데이트
        if daily_strategy.buy_amount is None:
            daily_strategy.buy_amount = 0.0
        daily_strategy.buy_amount += order_amount

        logger.info(
            f"BUY signal processed: stock_code={stock_code}, "
            f"buy_price={recommended_order_price:.2f}, quantity={target_quantity}"
        )

_handler_instance: Optional[OrderSignalHandler] = None
def get_order_signal_handler() -> OrderSignalHandler:
    """Order Signal Handler 싱글톤 인스턴스 반환"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = OrderSignalHandler()
    return _handler_instance