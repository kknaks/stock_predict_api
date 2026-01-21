from app.repositories.strategy_repository import StrategyRepository
from app.api.deps import DbSession

class HistoryService:
    def __init__(self, db: DbSession):
        self.db = db
        self.repo = StrategyRepository(db)

    async def get_monthly_history(self, user_id: int, date: str):
        # 이번달 필터링
        
        # user_strategy_id 필터링
        user_strategies = await self.repo.get_user_active_strategies(user_id)
        user_strategy_ids = [user_strategy.id for user_strategy in user_strategies]
        
        # daily_strategy_id 필터링
        daily_strategies = await self.repo.get_daily_strategies(user_strategy_ids, month_start, date)
        
        # daily_strategy_stock_id 필터링
        daily_strategy_stocks = await self.repo.get_daily_strategy_stocks(daily_strategy_ids)


