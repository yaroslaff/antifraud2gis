from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import mapped_column, relationship, Mapped
from typing import Optional
from datetime import datetime


from ..base import Base

class Metric(Base):
    __tablename__ = "metric"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_company_metric_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    string_value: Mapped[str] = mapped_column(String, nullable=True)
    region_id: Mapped[int] = mapped_column(Integer, nullable=False)

    company_id: Mapped[str] = mapped_column(ForeignKey("company.object_id"), nullable=False)
    company: Mapped["Company"] = relationship(back_populates="metrics")

    def __repr__(self):
        if self.value:
            return f'{self.company_id} r{self.region_id} {self.name} = {self.value}'
        elif self.string_value:
            return f'{self.company_id} r{self.region_id} {self.name} = "{self.string_value}"'
        else:
            return f'{self.company_id} r{self.region_id} {self.name} = N/A'
    