from app.repositories.predict_repository import PredictRepository
from app.schemas.predict import PredictionItem
from app.api.deps import DbSession


class PredictService:
    def __init__(self, db: DbSession):
        self.db = db
        self.repo = PredictRepository(db)

    async def get_predict_list(self, date: str) -> list[PredictionItem]:
        """예측 목록 조회"""
        predictions = await self.repo.get_predict_list(date)
        return [PredictionItem.model_validate(pred) for pred in predictions]