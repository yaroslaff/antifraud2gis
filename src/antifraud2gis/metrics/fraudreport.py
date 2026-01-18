from datetime import datetime, timezone
from dataclasses import dataclass
from ..models.company import Company
from ..models.metricperc import MetricPerc
from ..metrics import metrics_all, metrics_high, metrics_low
from ..db import DBSession, Session
from ..exceptions import AFNoCompany


from dataclasses import dataclass

@dataclass
class MetricResult:
    name: str
    value: float | None
    stars_hit: int
    stars_total: int


class FraudReport:
    object_id: str
    region_id: int
    c: Company
    control_region_id: int | None

    metrics_local: dict[str, MetricResult]
    metrics_control: dict[str, MetricResult]
    metrics_final: dict[str, MetricResult]

    def __init__(self,  c: Company, control_region_id: int, dbsession: Session):
        self.company = c

        control_region_id = control_region_id or 1

        if not c:
            raise AFNoCompany(f"Company {object_id} not found")
        
        print("Report for company:", c)

        if MetricPerc.need_recalculate(c.region_id, dbsession):
                print("Recalculating percentiles...")
                with DBSession() as dbsession2:
                    MetricPerc.recalculate(c.region_id, dbsession2)
                    dbsession2.commit()
        
        self.metrics_local = self.report(c.region_id, dbsession=dbsession)
        self.metrics_control = self.report(control_region_id, dbsession=dbsession)

        # make final metrics, as min between local and control
        self.metrics_final = dict()
        for metric in metrics_all:
            ml = self.metrics_local.get(metric)
            mc = self.metrics_control.get(metric)

            if ml is None or mc is None:
                raise ValueError(f"Metric {metric} not found in local or control reports")

            # both present, take min stars hit
            if ml.stars_hit <= mc.stars_hit:
                self.metrics_final[metric] = ml
            else:
                self.metrics_final[metric] = mc

        

    def report(self, region_id: int, dbsession: Session) -> dict[str, MetricResult]:

        metrics_report: dict[str, MetricResult] = dict()

        #print("report for region:", region_id)

        for metric in metrics_all:
            stars_hit = 0
            stars_total = 0

            #print(f"Processing metric: {metric} in r{region_id}")

            m = self.company.get_metric(metric)
            if not m or m.value is None:
                print(f"  Metric {metric} not found or has no value")
                continue
            # print(f"  Metric {metric} = {m.value}")

            # get percentiles for city
            for mp in dbsession.query(MetricPerc).filter(
                MetricPerc.region_id == region_id,
                MetricPerc.name == metric,
            ).all():
                stars_total += 1

                if metric in metrics_high:
                    # normal, high metric
                    if m.value > mp.value:
                        stars_hit += 1
                else:
                    # low metric
                    # normal, high metric
                    if m.value < mp.value:
                        stars_hit += 1

            # print(f"  {metric} ({m.value}): {stars_hit}/{stars_total} stars hit")
            metrics_report[metric] = MetricResult(
                name=metric,
                value=m.value,
                stars_hit=stars_hit,
                stars_total=stars_total
            )
        return metrics_report
        
    def dump(self):
        print(f"Fraud Report for company {self.company.object_id} ({self.company.title})")
        for metric in metrics_all:
            ml = self.metrics_local.get(metric)
            mc = self.metrics_control.get(metric)
            mf = self.metrics_final.get(metric)
            print(f"Final {metric}: {mf.stars_hit}/{mf.stars_total} stars hit (value={mf.value}) Lr:{ml.stars_hit} / Cr:{mc.stars_hit}")