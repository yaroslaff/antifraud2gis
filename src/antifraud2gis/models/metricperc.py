""" percentiles for metrics """

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import mapped_column, relationship, Mapped, Session

from datetime import datetime, timezone
import numpy as np

from ..base import Base
from ..db import DBSession
from ..models.metric import Metric
from ..models.metric import Metric
from ..metrics import metrics_all, metrics_high, metrics_low, percentiles_values



class MetricPerc(Base):
    __tablename__ = "metricperc"
    __table_args__ = (UniqueConstraint("region_id", "name", "p", name="uq_region_id_name_p"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    region_id: Mapped[int] = mapped_column(Integer, nullable=False)

    p: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    calculated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=None, nullable=True)
    comment: Mapped[str] = mapped_column(String, nullable=True)
    
    def __repr__(self):
        return f'{self.name}({self.city}r:{self.region_id}) p{self.p} = {self.value} ({self.calculated}) {self.comment}'

    @classmethod
    def get(cls, region_id: int, name: str, p: int, dbsession: Session) -> "MetricPerc | None":
        stmt = (
            select(MetricPerc)
            .where(
                MetricPerc.region_id == region_id,
                MetricPerc.name == name,
                MetricPerc.p == p
            )
        )
        
        mp = dbsession.scalar(stmt)
        return mp

    @classmethod
    def need_recalculate(cls, region_id: int, dbsession: Session) -> bool:
        num_mp = dbsession.query(cls).filter(cls.region_id == region_id).count()
        return num_mp == 0
    
    @classmethod
    def recalculate(cls, region_id: int, dbsession: Session):
        for metric in metrics_all:
            for percentile in percentiles_values:

                # print(f"calc percentile {percentile} for {metric} r{region_id}...")

                if metric in metrics_high:
                    pval = percentile
                else:
                    pval = 100 - percentile

                pval = round(pval, 2)

                values = dbsession.scalars(
                    select(Metric.value)
                    .join(Metric.company)
                    .where(
                        Metric.name == metric, 
                        Metric.region_id == region_id,
                        Metric.value.isnot(None)
                        )
                ).all()

                p = round(np.percentile(values, pval), 2) if values else None

                if p is None:
                    print(f"  {metric} {pval}% percentile = N/A (no values in database for r{region_id})")
                    continue
                print(f"  {metric} {pval}% percentile = {p} from {len(values)} values")

                # try fetch existing percentile
                mp = MetricPerc.get(region_id=region_id, name=metric, p=pval, dbsession=dbsession)
                if mp:
                    mp.value = p
                    mp.calculated = datetime.now(timezone.utc).replace(microsecond=0)
                    mp.comment = f'Based on {len(values)} metrics in r{region_id}'
                else:
                    # or make new
                    mp = MetricPerc(
                        city='',
                        region_id=region_id,
                        name=metric,
                        p=pval,
                        value=p,
                        calculated=datetime.now(timezone.utc).replace(microsecond=0),
                        comment = f'Based on {len(values)} metrics in r{region_id}'
                    )
                    dbsession.add(mp)

