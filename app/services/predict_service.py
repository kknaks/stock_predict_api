import logging
from datetime import datetime, date as date_type

from app.repositories.predict_repository import PredictRepository
from app.repositories.stock_repository import StockRepository
from app.schemas.predict import PredictionItem, StrategyWithPredictions, StrategyInfoSchema
from app.api.deps import DbSession
from app.services.price_cache import get_price_cache
from app.utils.market_time import is_market_open, is_today

logger = logging.getLogger(__name__)


class PredictService:
    def __init__(self, db: DbSession):
        self.db = db
        self.repo = PredictRepository(db)
        self.stock_repo = StockRepository(db)
        self.price_cache = get_price_cache()

    async def get_predict_list(self, date: str) -> list[PredictionItem]:
        """예측 목록 조회"""
        predictions = await self.repo.get_predict_list(date)
        return [PredictionItem.model_validate(pred) for pred in predictions]

    async def get_predict_by_type_all(self, date: str) -> list[StrategyWithPredictions]:
        """전략별로 그룹화하여 예측 목록 조회 (현재가 포함)"""
        strategies = await self.repo.get_predict_by_type_all(date)
        
        # 장중 여부 및 날짜 확인
        market_is_open = is_market_open()
        date_is_today = is_today(date)
        
        # 날짜 파싱
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            target_date = None
        
        result = []
        for strategy in strategies:
            predictions = []
            for pred in strategy.gap_predictions:
                pred_dict = PredictionItem.model_validate(pred).model_dump()
                
                # 현재가 조회
                current_price = None
                stock_code = pred_dict.get("stock_code")
                
                if stock_code:
                    # 장중이고 오늘이면 메모리 캐시에서 조회
                    if market_is_open and date_is_today:
                        cached_price = self.price_cache.get(stock_code)
                        if cached_price:
                            try:
                                current_price = float(cached_price.current_price)
                            except (ValueError, AttributeError):
                                pass
                    
                    # 장 마감 후나 이전 날이면 DB에서 종가 조회
                    if current_price is None and target_date:
                        closing_price = await self.stock_repo.get_closing_price(stock_code, target_date)
                        if closing_price:
                            current_price = float(closing_price)
                
                pred_dict["current_price"] = current_price
                predictions.append(PredictionItem(**pred_dict))
            
            # 후보군 필터링 및 제한 (prediction_handler와 동일한 로직)
            logger.info(f"[predict_service] Strategy {strategy.id}: {len(predictions)} predictions before filter")
            candidate_predictions = [
                p for p in predictions
                if p.gap_rate < 28 and p.prob_up > 0.2
            ]
            logger.info(f"[predict_service] Strategy {strategy.id}: {len(candidate_predictions)} predictions after filter (gap_rate<28 & prob_up>0.2)")
            candidate_predictions = sorted(
                candidate_predictions,
                key=lambda x: x.prob_up,
                reverse=True
            )[:15]

            result.append(
                StrategyWithPredictions(
                    strategy_info=StrategyInfoSchema.model_validate(strategy),
                    predictions=candidate_predictions
                )
            )

        logger.info(f"[predict_service] Returning {len(result)} strategies")
        return result