from sqlalchemy import String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import mapped_column, relationship, Mapped

from datetime import datetime

from ..base import Base

class Metric(Base):
    __tablename__ = "metric"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_company_metric_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    company_id: Mapped[str] = mapped_column(ForeignKey("company.object_id"), nullable=False)
    company: Mapped["Company"] = relationship(back_populates="metrics")

    def __repr__(self):
        return f'{self.company_id} {self.name} = {self.value}'
    