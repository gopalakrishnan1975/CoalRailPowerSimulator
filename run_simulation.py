"""Reproducible headless run: python run_simulation.py --days 60 --output results"""
import argparse,json
from pathlib import Path
from dataclasses import replace
from coalpower.model import Config,load_network
from coalpower.engine import simulate
p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=60);p.add_argument('--seed',type=int,default=42);p.add_argument('--output',default='results');a=p.parse_args()
network=load_network();r=simulate(network,Config(days=a.days,seed=a.seed));out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
(out/'network.json').write_text(json.dumps(network,indent=2))
(out/'summary.json').write_text(json.dumps(r['summary'],indent=2))
for name in ['daily','stocks','prices','events']:r[name].to_csv(out/(name+'.csv'),index=False)
print(json.dumps(r['summary'],indent=2))
