"""
주문 결과 메시지 핸들러

주문 접수 및 체결통보 메시지를 처리하여 Order와 OrderExecution 테이블에 저장
"""

import logging
import asyncio
from typing import Optional
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.config.db_connections import get_session_factory
from app.schemas.order_signal import OrderResultMessage
from app.repositories.stock_repository import StockRepository
from app.services.kis_service import KISService
from app.database.database.strategy import (
    DailyStrategy as DailyStrategyModel,
    DailyStrategyStock as DailyStrategyStockModel,
    Order as OrderModel,
    OrderExecution as OrderExecutionModel,
    OrderStatus,
    OrderType,
)
from app.database.database.users import AccountType
from app.utils.rate_limiter import get_account_rate_limiter

logger = logging.getLogger(__name__)


class OrderResultHandler:
    """주문 결과 메시지 핸들러"""

    def __init__(self):
        self._session_factory = get_session_factory()
        # order_no별 처리 lock - 같은 주문의 체결통보를 순차 처리
        self._order_locks: dict[str, asyncio.Lock] = {}

    def _get_order_lock(self, order_no: str) -> asyncio.Lock:
        """주문번호별 Lock 반환 (없으면 생성)"""
        if order_no not in self._order_locks:
            self._order_locks[order_no] = asyncio.Lock()
        return self._order_locks[order_no]

    def _cleanup_order_lock(self, order_no: str) -> None:
        """완료된 주문의 Lock 정리"""
        self._order_locks.pop(order_no, None)

    async def handle_order_result(self, message: OrderResultMessage, max_retries: int = 5) -> None:
        """
        주문 결과 메시지 처리 및 데이터베이스 저장

        같은 order_no에 대한 메시지를 asyncio.Lock으로 직렬화하여
        DB row-level lock 경합 없이 순차 처리.
        """
        logger.info(
            f"Processing order result message: order_no={message.order_no}, "
            f"status={message.status}, user_strategy_id={message.user_strategy_id}, "
            f"total_executed_quantity={message.total_executed_quantity}"
        )

        # 같은 주문번호에 대한 메시지를 순차 처리
        lock = self._get_order_lock(message.order_no)
        async with lock:
            for attempt in range(max_retries):
                try:
                    await self._process_order_result(message)
                    # 전량 체결 완료 시 lock 정리
                    if message.is_fully_executed:
                        self._cleanup_order_lock(message.order_no)
                    return
                except IntegrityError as e:
                    logger.warning(
                        f"IntegrityError on attempt {attempt + 1}/{max_retries} "
                        f"for order_no={message.order_no}: {e}"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.1 * (attempt + 1))
                    else:
                        logger.error(
                            f"Failed to process order result after {max_retries} attempts: "
                            f"order_no={message.order_no}"
                        )
                        raise
                except Exception as e:
                    logger.error(
                        f"Error processing order result (attempt {attempt + 1}/{max_retries}): "
                        f"order_no={message.order_no}, error={e}",
                        exc_info=True
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.1 * (attempt + 1))
                    else:
                        raise

    async def _process_order_result(self, message: OrderResultMessage) -> None:
        """실제 주문 결과 처리 로직"""
        session: Optional[AsyncSession] = None
        try:
            session = self._session_factory()
            stock_repository = StockRepository(session)

            # timestamp를 datetime으로 변환
            if isinstance(message.timestamp, str):
                timestamp = datetime.fromisoformat(message.timestamp.replace('Z', '+00:00'))
            else:
                timestamp = message.timestamp

            # DailyStrategyStock 찾기
            order_date = timestamp.date()
            daily_strategy = await stock_repository.get_daily_strategy_with_stocks(
                message.user_strategy_id, order_date
            )

            if not daily_strategy:
                logger.warning(
                    f"DailyStrategy not found: user_strategy_id={message.user_strategy_id}, "
                    f"date={order_date}"
                )
                return

            # 해당 종목 찾기
            daily_strategy_stock = None
            for stock in daily_strategy.stocks:
                if stock.stock_code == message.stock_code:
                    daily_strategy_stock = stock
                    break

            if not daily_strategy_stock:
                logger.warning(
                    f"DailyStrategyStock not found: stock_code={message.stock_code}, "
                    f"daily_strategy_id={daily_strategy.id}"
                )
                return

            # 주문번호로 기존 Order 조회
            stmt = select(OrderModel).where(
                OrderModel.order_no == message.order_no
            ).with_for_update()
            result = await session.execute(stmt)
            existing_order = result.scalar_one_or_none()

            if message.status == "ordered":
                # 주문 접수: Order 테이블에 새 레코드 생성
                if existing_order:
                    logger.warning(
                        f"Order already exists: order_no={message.order_no}, updating..."
                    )
                    existing_order.order_quantity = message.order_quantity
                    existing_order.order_price = message.order_price
                    existing_order.order_dvsn = message.order_dvsn
                    existing_order.status = OrderStatus.ORDERED
                    existing_order.total_executed_quantity = 0
                    existing_order.total_executed_price = 0.0
                    existing_order.remaining_quantity = message.order_quantity
                    existing_order.is_fully_executed = False
                    existing_order.ordered_at = timestamp
                else:
                    new_order = OrderModel(
                        daily_strategy_stock_id=daily_strategy_stock.id,
                        order_no=message.order_no,
                        order_type=OrderType.BUY if message.order_type == "BUY" else OrderType.SELL,
                        order_quantity=message.order_quantity,
                        order_price=message.order_price,
                        order_dvsn=message.order_dvsn,
                        account_no=message.account_no,
                        is_mock=message.is_mock,
                        status=OrderStatus.ORDERED,
                        total_executed_quantity=0,
                        total_executed_price=0.0,
                        remaining_quantity=message.order_quantity,
                        is_fully_executed=False,
                        ordered_at=timestamp,
                    )
                    session.add(new_order)
                    logger.info(
                        f"Created new order: order_no={message.order_no}, "
                        f"order_type={message.order_type}, quantity={message.order_quantity}"
                    )
            else:
                # 체결통보: 기존 Order 업데이트 및 OrderExecution 생성
                if not existing_order:
                    logger.warning(
                        f"Order not found for execution: order_no={message.order_no}, "
                        f"creating order first..."
                    )
                    existing_order = OrderModel(
                        daily_strategy_stock_id=daily_strategy_stock.id,
                        order_no=message.order_no,
                        order_type=OrderType.BUY if message.order_type == "BUY" else OrderType.SELL,
                        order_quantity=message.order_quantity,
                        order_price=message.order_price,
                        order_dvsn=message.order_dvsn,
                        account_no=message.account_no,
                        is_mock=message.is_mock,
                        status=OrderStatus.PARTIALLY_EXECUTED if message.status == "partially_executed" else OrderStatus.EXECUTED,
                        total_executed_quantity=message.total_executed_quantity,
                        total_executed_price=message.total_executed_price,
                        remaining_quantity=message.remaining_quantity,
                        is_fully_executed=message.is_fully_executed,
                        ordered_at=timestamp,
                    )
                    session.add(existing_order)
                    await session.flush()
                else:
                    # 누적 체결수량이 DB보다 큰 경우에만 업데이트 (idempotent)
                    if message.total_executed_quantity >= (existing_order.total_executed_quantity or 0):
                        existing_order.status = (
                            OrderStatus.PARTIALLY_EXECUTED
                            if message.status == "partially_executed"
                            else OrderStatus.EXECUTED
                        )
                        existing_order.total_executed_quantity = message.total_executed_quantity
                        existing_order.total_executed_price = message.total_executed_price
                        existing_order.remaining_quantity = message.remaining_quantity
                        existing_order.is_fully_executed = message.is_fully_executed
                    else:
                        logger.warning(
                            f"Skipping stale message: order_no={message.order_no}, "
                            f"msg_total={message.total_executed_quantity}, "
                            f"db_total={existing_order.total_executed_quantity}"
                        )

                # 체결 순서 계산 (count 기반으로 중복 sequence 방지)
                count_stmt = select(func.count()).select_from(OrderExecutionModel).where(
                    OrderExecutionModel.order_id == existing_order.id
                )
                count_result = await session.execute(count_stmt)
                execution_count = count_result.scalar() or 0
                execution_sequence = execution_count + 1

                # OrderExecution 생성
                new_execution = OrderExecutionModel(
                    order_id=existing_order.id,
                    execution_sequence=execution_sequence,
                    executed_quantity=message.executed_quantity,
                    executed_price=message.executed_price,
                    total_executed_quantity_after=message.total_executed_quantity,
                    total_executed_price_after=message.total_executed_price,
                    remaining_quantity_after=message.remaining_quantity,
                    is_fully_executed_after=message.is_fully_executed,
                    executed_at=timestamp,
                )
                session.add(new_execution)
                logger.info(
                    f"Created order execution: order_no={message.order_no}, "
                    f"sequence={execution_sequence}, "
                    f"executed_quantity={message.executed_quantity}, "
                    f"total_executed_quantity={message.total_executed_quantity}"
                )

                # 체결 시마다 DailyStrategyStock 업데이트 (부분 체결 포함)
                await self._update_daily_strategy_stock(
                    session,
                    daily_strategy_stock,
                    daily_strategy,
                    existing_order,
                    message.order_type
                )
                # 체결분만큼 Account balance 반영 (이번 체결 delta만)
                await self._update_account_balance_on_execution(
                    session,
                    daily_strategy,
                    existing_order,
                    message.order_type,
                    executed_quantity=message.executed_quantity,
                    executed_price=message.executed_price,
                )

            await session.commit()
            logger.info(f"Successfully processed order result: order_no={message.order_no}")

        except Exception as e:
            logger.error(f"Error processing order result: {e}", exc_info=True)
            if session:
                await session.rollback()
            raise
        finally:
            if session:
                await session.close()

    async def _update_daily_strategy_stock(
        self,
        session: AsyncSession,
        daily_strategy_stock: DailyStrategyStockModel,
        daily_strategy: DailyStrategyModel,
        order: OrderModel,
        order_type: str
    ) -> None:
        """
        체결 시마다 DailyStrategyStock 및 DailyStrategy 업데이트 (부분 체결 포함)
        """
        if order_type == "BUY":
            daily_strategy_stock.buy_price = order.total_executed_price
            daily_strategy_stock.buy_quantity = float(order.total_executed_quantity)

            logger.info(
                f"Updated DailyStrategyStock buy info: stock_code={daily_strategy_stock.stock_code}, "
                f"buy_price={order.total_executed_price:.2f}, "
                f"buy_quantity={order.total_executed_quantity}, "
                f"is_fully_executed={order.is_fully_executed}"
            )

            await session.flush()

            stmt = select(
                func.sum(DailyStrategyStockModel.buy_price * DailyStrategyStockModel.buy_quantity)
            ).where(
                DailyStrategyStockModel.daily_strategy_id == daily_strategy.id,
                DailyStrategyStockModel.buy_price.isnot(None),
                DailyStrategyStockModel.buy_quantity.isnot(None)
            )
            result = await session.execute(stmt)
            total_buy_amount = result.scalar() or 0.0
            daily_strategy.buy_amount = total_buy_amount

        elif order_type == "SELL":
            daily_strategy_stock.sell_price = order.total_executed_price
            daily_strategy_stock.sell_quantity = float(order.total_executed_quantity)

            if daily_strategy_stock.buy_price and daily_strategy_stock.buy_quantity:
                profit_rate = ((order.total_executed_price - daily_strategy_stock.buy_price) / daily_strategy_stock.buy_price) * 100
                daily_strategy_stock.profit_rate = profit_rate

                actual_quantity = min(order.total_executed_quantity, int(daily_strategy_stock.buy_quantity))
                profit_amount = (order.total_executed_price - daily_strategy_stock.buy_price) * actual_quantity

                logger.info(
                    f"Updated DailyStrategyStock sell info: stock_code={daily_strategy_stock.stock_code}, "
                    f"sell_price={order.total_executed_price:.2f}, "
                    f"sell_quantity={order.total_executed_quantity}, "
                    f"profit_rate={profit_rate:.2f}%, "
                    f"profit_amount={profit_amount:.2f}, "
                    f"is_fully_executed={order.is_fully_executed}"
                )
            else:
                logger.warning(
                    f"SELL execution but buy_price/buy_quantity not set: "
                    f"stock_code={daily_strategy_stock.stock_code}"
                )

            await session.flush()

            stmt = select(
                func.sum(DailyStrategyStockModel.sell_price * DailyStrategyStockModel.sell_quantity)
            ).where(
                DailyStrategyStockModel.daily_strategy_id == daily_strategy.id,
                DailyStrategyStockModel.sell_price.isnot(None),
                DailyStrategyStockModel.sell_quantity.isnot(None)
            )
            result = await session.execute(stmt)
            total_sell_amount = result.scalar() or 0.0
            daily_strategy.sell_amount = total_sell_amount

            profit_stmt = select(
                func.sum(
                    (DailyStrategyStockModel.sell_price - DailyStrategyStockModel.buy_price)
                    * func.least(DailyStrategyStockModel.sell_quantity, DailyStrategyStockModel.buy_quantity)
                )
            ).where(
                DailyStrategyStockModel.daily_strategy_id == daily_strategy.id,
                DailyStrategyStockModel.buy_price.isnot(None),
                DailyStrategyStockModel.buy_quantity.isnot(None),
                DailyStrategyStockModel.sell_price.isnot(None),
                DailyStrategyStockModel.sell_quantity.isnot(None)
            )
            profit_result = await session.execute(profit_stmt)
            daily_strategy.total_profit_amount = profit_result.scalar() or 0.0

            buy_stmt = select(
                func.sum(DailyStrategyStockModel.buy_price * DailyStrategyStockModel.buy_quantity)
            ).where(
                DailyStrategyStockModel.daily_strategy_id == daily_strategy.id,
                DailyStrategyStockModel.buy_price.isnot(None),
                DailyStrategyStockModel.buy_quantity.isnot(None)
            )
            buy_result = await session.execute(buy_stmt)
            total_buy_amount = buy_result.scalar() or 0.0

            if total_buy_amount > 0:
                daily_strategy.total_profit_rate = (daily_strategy.total_profit_amount / total_buy_amount) * 100

    async def _update_account_balance_on_execution(
        self,
        session: AsyncSession,
        daily_strategy: DailyStrategyModel,
        order: OrderModel,
        order_type: str,
        executed_quantity: int,
        executed_price: float,
    ) -> None:
        """
        체결 시마다 Account balance 반영 (이번 체결분 delta만).
        """
        account = daily_strategy.user_strategy.account
        delta_amount = float(executed_price * executed_quantity)

        if account.account_type == AccountType.MOCK:
            balance = float(account.account_balance) if account.account_balance is not None else 0.0
            if order_type == "BUY":
                account.account_balance = balance - delta_amount
            else:
                account.account_balance = balance + delta_amount
            logger.info(
                f"Updated MOCK account balance: account_id={account.id}, "
                f"order_type={order_type}, delta={-delta_amount if order_type == 'BUY' else delta_amount:+.0f}, "
                f"balance={account.account_balance}"
            )
        elif account.account_type in (AccountType.PAPER, AccountType.REAL):
            is_paper = account.account_type == AccountType.PAPER

            rate_limiter = get_account_rate_limiter(account.id, is_paper)
            await rate_limiter._wait_if_needed_async()

            kis = KISService(account.app_key, account.app_secret, is_paper=is_paper)
            if account.is_token_valid() and account.kis_access_token:
                kis.access_token = account.kis_access_token
            else:
                await kis.get_access_token()
                account.kis_access_token = kis.access_token
                account.kis_token_expired_at = kis.token_expired_at
            try:
                balance_data = await kis.get_account_balance(account.account_number)
                if balance_data.get("rt_cd") == "0" and balance_data.get("output2"):
                    cash_balance = int(
                        balance_data["output2"][0].get("dnca_tot_amt", 0)
                    )
                    account.account_balance = cash_balance
                    logger.info(
                        f"Updated PAPER/REAL account balance from KIS (예수금): "
                        f"account_id={account.id}, balance={cash_balance}"
                    )
                else:
                    logger.warning(
                        f"KIS balance inquiry failed or empty output2: "
                        f"account_id={account.id}, "
                        f"rt_cd={balance_data.get('rt_cd', 'N/A')}"
                    )
            except Exception as e:
                logger.warning(
                    f"KIS balance inquiry error, skip balance update: "
                    f"account_id={account.id}, error={e}"
                )


_handler_instance: Optional[OrderResultHandler] = None


def get_order_result_handler() -> OrderResultHandler:
    """Order Result Handler 싱글톤 인스턴스 반환"""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = OrderResultHandler()
    return _handler_instance
