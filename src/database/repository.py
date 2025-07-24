
from abc import ABC, abstractmethod
from typing import Any, Dict

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class AbstractRepository(ABC):
    @abstractmethod
    async def add_one(self, data: dict):
        raise NotImplementedError

    @abstractmethod
    async def find_all(self):
        raise NotImplementedError

    @abstractmethod
    async def get_one(self, model_id: int):
        raise NotImplementedError

    @abstractmethod
    async def update_one(self, model_id: int, data: Dict[str, Any]):
        raise NotImplementedError

    @abstractmethod
    async def delete_one(self, profile_id: int):
        raise NotImplementedError


class BaseRepository(AbstractRepository):
    def __init__(self, model, session: AsyncSession):
        self.model = model
        self.session = session

    async def add_one(self, data: dict):
        stmt = insert(self.model).values(**data).returning(self.model)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.scalar_one()

    async def find_all(self, filters: Dict[str, Any] = None):
        stmt = select(self.model)

        if filters:
            for field, value in filters.items():
                stmt = stmt.where(getattr(self.model, field) == value)

        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def get_one(self, model_id: int):
        stmt = select(self.model).where(self.model.id == model_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_one(self, model_id: int, data: Dict[str, Any]):
        stmt = (
            update(self.model)
            .where(self.model.id == model_id)
            .values(**data)
            .returning(self.model)
        )
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.scalar_one_or_none()

    async def delete_one(self, profile_id: int):
        stmt = delete(self.model).where(self.model.id == profile_id)
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount > 0
