"""Validated, JSON-serializable master data and experiment configuration."""
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import math

@dataclass
class Config:
    days: int = 90
    seed: int = 42
    demand_mw: float = 1800
    demand_volatility: float = .12
    solar_mw: float = 1100
    wind_mw: float = 450
    wind_cf: float = .35
    renewable_volatility: float = .25
    shock_probability: float = .08
    shock_severity: float = .5
    annual_carry_rate: float = .12
    plant_cover_days: float = 10
    mine_cover_days: float = 5
    pithead_share: float = .35
    coal_markup: float = 200
    rail_premium: float = 60
    congestion_gain: float = 100
    price_smoothing: float = .25
    availability_payment: float = 2
    performance_penalty_mwh: float = 2000
    value_lost_load_mwh: float = 100000
    electricity_price_cap: float = 12000
    carbon_cost_mwh: float = 0
    fleet_rakes: int = 45
    rake_tonnes: float = 4000
    empty_return_days: int = 2
    policy: str = 'dynamic'
    safety_quantile: float = .95
    def validate(self):
        for k,v in asdict(self).items():
            if isinstance(v,(int,float)) and (not math.isfinite(v) or v < 0):
                raise ValueError(f'{k} must be finite and nonnegative')
        for k in ['days','seed','fleet_rakes','empty_return_days']:
            if not isinstance(getattr(self,k),int):
                raise ValueError(f'{k} must be an integer')
        if not 1 <= self.days <= 365 or not 1 <= self.fleet_rakes <= 1000:
            raise ValueError('days must be 1..365 and fleet_rakes 1..1000')
        if self.rake_tonnes <= 0 or self.demand_mw <= 0:
            raise ValueError('rake_tonnes and demand_mw must be positive')
        for k in ['pithead_share','shock_probability','shock_severity','wind_cf','price_smoothing','safety_quantile']:
            if not 0 <= getattr(self,k) <= 1:
                raise ValueError(f'{k} must be between 0 and 1')
        if self.policy not in ['static','dynamic','coordinated']:
            raise ValueError('policy must be static, dynamic or coordinated')

FIELDS = {
 'mines': ['mine_id','production_tpd','initial_stock_t','capacity_t','coal_price_t','mining_cost_t','storage_cost_t_day'],
 'plants': ['plant_id','capacity_mw','initial_stock_t','capacity_t','mwh_per_t','nonfuel_cost_mwh','storage_cost_t_day'],
 'routes': ['route_id','mine_id','plant_id','corridor_id','lead_days','rakes_per_day','freight_t','real_transport_cost_t'],
 'corridors': ['corridor_id','rakes_per_day'],
}
IDS = {'mines':'mine_id','plants':'plant_id','routes':'route_id','corridors':'corridor_id'}

def load_network(folder=None):
    folder = Path(folder or Path(__file__).resolve().parents[1] / 'data')
    data = {}
    for name in FIELDS:
        with (folder / f'{name}.csv').open() as f:
            data[name] = list(csv.DictReader(f))
        for row in data[name]:
            for k in row:
                if not k.endswith('_id'):
                    row[k] = float(row[k])
    validate_network(data)
    return data

def validate_network(data):
    for table, fields in FIELDS.items():
        rows = data.get(table,[])
        if not rows:
            raise ValueError(f'{table} cannot be empty')
        ids=[]
        for row in rows:
            missing=set(fields)-set(row)
            if missing:
                raise ValueError(f'{table}: missing {sorted(missing)}')
            ids.append(row[IDS[table]])
            if not isinstance(ids[-1],str) or not ids[-1].strip():
                raise ValueError(f'{table}: IDs must be nonempty strings')
            for k in fields:
                if not k.endswith('_id'):
                    v=row[k]
                    if not isinstance(v,(int,float)) or not math.isfinite(v) or v<0:
                        raise ValueError(f'{table}.{k}: finite nonnegative number required')
            if table in ['mines','plants'] and row['initial_stock_t'] > row['capacity_t']:
                raise ValueError(f'{table}: initial stock exceeds storage capacity')
            if table=='plants' and (row['mwh_per_t']<=0 or row['capacity_mw']<=0):
                raise ValueError('Plant capacity and conversion must be positive')
            if table=='routes' and (row['lead_days']<1 or row['lead_days']!=int(row['lead_days'])):
                raise ValueError('Route lead_days must be an integer >= 1')
        if len(set(ids)) != len(ids):
            raise ValueError(f'{table}: duplicate IDs')
    location_ids=[r['mine_id'] for r in data['mines']]+[r['plant_id'] for r in data['plants']]
    if len(set(location_ids))!=len(location_ids) or 'Railways' in location_ids:
        raise ValueError('Mine and plant IDs must be globally distinct and cannot be Railways')
    for r in data['routes']:
        for key,table in [('mine_id','mines'),('plant_id','plants'),('corridor_id','corridors')]:
            if r[key] not in {x[IDS[table]] for x in data[table]}:
                raise ValueError(f'Unknown {key}: {r[key]}')
    for p in data['plants']:
        if not any(r['plant_id']==p['plant_id'] for r in data['routes']):
            raise ValueError(f'Plant {p["plant_id"]} has no supply route')
