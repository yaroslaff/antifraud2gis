from sqlalchemy import String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import mapped_column, relationship, Mapped

from datetime import datetime

from ..base import Base

class AuthorMetric(Base):
    __tablename__ = "authormetric"
    __table_args__ = (UniqueConstraint("author_id", "name", name="uq_author_metric_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ### name of metric, e.g. "traveller"
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=True)

    author_id: Mapped[str] = mapped_column(ForeignKey("author.public_id"), nullable=False)
    # author: Mapped["Author"] = relationship(back_populates="metrics")

    def __repr__(self):
        return f'{self.author_id} {self.name} = {self.value}'


