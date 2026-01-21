from datetime import datetime, date
from calendar import monthrange
from typing import List

from app.repositories.strategy_repository import StrategyRepository
from app.repositories.account_repository import AccountRepository
from app.api.deps import DbSession
from app.schemas.history import HistoryResponse, AccountHistoryResponse, DailyHistory


class HistoryService:
    def __init__(self, db: DbSession):
        self.db = db
        self.repo = StrategyRepository(db)
        self.account_repo = AccountRepository(db)

    async def get_monthly_history(self, user_id: int, date_str: str) -> HistoryResponse:
        """
        월별 히스토리 조회 (사용자의 모든 계좌)

        Args:
            user_id: 사용자 ID
            date_str: 조회 기준 날짜 (YYYY-MM-DD)

        Returns:
            HistoryResponse: 계좌별 월간 히스토리 데이터
        """
        # 날짜 파싱
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        year = target_date.year
        month = target_date.month

        # 월의 시작일과 마지막일
        month_start = date(year, month, 1)
        _, last_day = monthrange(year, month)
        month_end = date(year, month, last_day)

        # 사용자의 모든 계좌 조회
        accounts = await self.account_repo.get_by_user_uid(user_id)

        account_histories = []
        for account in accounts:
            history = await self._get_account_history(
                account, month_start, month_end
            )
            account_histories.append(history)

        return HistoryResponse(
            year=year,
            month=month,
            accounts=account_histories,
        )

    async def _get_account_history(
        self,
        account,
        month_start: date,
        month_end: date
    ) -> AccountHistoryResponse:
        """개별 계좌의 월간 히스토리 조회"""
        # 계좌의 전략 조회 (삭제되지 않은 것만)
        strategies = await self.repo.get_account_active_strategies(account.id)

        if not strategies:
            return AccountHistoryResponse(
                account_id=account.id,
                account_number=account.account_number,
                account_name=account.account_name or "",
            )

        strategy_ids = [s.id for s in strategies]

        # 월별 DailyStrategy 조회
        daily_strategies = await self.repo.get_monthly_daily_strategies(
            strategy_ids, month_start, month_end
        )

        # 일별 히스토리 생성
        daily_histories = []
        cumulative_profit_rate = 0.0
        cumulative_profit_amount = 0.0
        total_buy_amount = 0.0
        total_sell_amount = 0.0

        for ds in daily_strategies:
            daily_profit_rate = ds.total_profit_rate or 0.0
            daily_profit_amount = ds.total_profit_amount or 0.0
            daily_buy_amount = ds.buy_amount or 0.0
            daily_sell_amount = ds.sell_amount or 0.0

            # 누적 수익률 계산 (복리)
            if cumulative_profit_rate == 0:
                cumulative_profit_rate = daily_profit_rate
            else:
                cumulative_profit_rate = (
                    (1 + cumulative_profit_rate / 100) * (1 + daily_profit_rate / 100) - 1
                ) * 100

            # 누적 수익금 계산
            cumulative_profit_amount += daily_profit_amount

            # 합계 계산
            total_buy_amount += daily_buy_amount
            total_sell_amount += daily_sell_amount

            daily_histories.append(
                DailyHistory(
                    date=ds.timestamp.strftime("%Y-%m-%d"),
                    profit_rate=round(daily_profit_rate, 2),
                    profit_amount=round(daily_profit_amount, 0),
                    cumulative_profit_rate=round(cumulative_profit_rate, 2),
                    cumulative_profit_amount=round(cumulative_profit_amount, 0),
                    buy_amount=round(daily_buy_amount, 0),
                    sell_amount=round(daily_sell_amount, 0),
                )
            )

        return AccountHistoryResponse(
            account_id=account.id,
            account_number=account.account_number,
            account_name=account.account_name or "",
            total_profit_rate=round(cumulative_profit_rate, 2),
            total_profit_amount=round(cumulative_profit_amount, 0),
            total_buy_amount=round(total_buy_amount, 0),
            total_sell_amount=round(total_sell_amount, 0),
            trading_days=len(daily_histories),
            daily_histories=daily_histories,
        )
