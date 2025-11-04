""" percentiles for metrics """

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import mapped_column, relationship, Mapped, Session

from datetime import datetime

from ..base import Base

class MetricPerc(Base):
    __tablename__ = "metricperc"
    __table_args__ = (UniqueConstraint("city", "name", "p", name="uq_city_name_p"),)


    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    p: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    calculated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=None, nullable=True)

    def __repr__(self):
        return f'{self.name}({self.city}) p{self.p} = {self.value} ({self.calculated})'

    @classmethod
    def get(cls, city: str, name: str, p: int, dbsession: Session) -> "MetricPerc":
        mp = dbsession.scalar(
            select(MetricPerc)
            .where(
                MetricPerc.city == city,
                MetricPerc.name == name,
                MetricPerc.p == p
            )
        )        
        return mp
