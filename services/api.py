"""Optional research-service adapters. No auth: bind only to localhost/trusted network."""
import os
from dataclasses import asdict
import json
from fastapi import FastAPI,Body,HTTPException
from coalpower.model import Config,load_network,validate_network
from coalpower.engine import simulate,forecast_burn,mechanism_search
from coalpower.game import best_response_lab

ROLE=os.environ.get('SERVICE_ROLE','simulation')
if ROLE not in ['catalog','forecast','simulation','game']:raise ValueError('Invalid SERVICE_ROLE')
app=FastAPI(title=f'Coal power {ROLE} service',version='0.1.0')

def inputs(payload):
    try:
        if len(json.dumps(payload))>2_000_000:raise ValueError('Request exceeds research service size limit')
        net=payload.get('network') or load_network();validate_network(net)
        if len(net['plants'])>30 or len(net['mines'])>30 or len(net['routes'])>300:raise ValueError('Research service network limit exceeded')
        cfg=Config(**payload.get('config',{}));cfg.validate()
        return net,cfg
    except (ValueError,TypeError,KeyError) as e:raise HTTPException(422,str(e)) from e

def records(df):
    return json.loads(df.to_json(orient='records'))

@app.get('/health')
def health():return {'status':'ok','role':ROLE,'version':'0.1.0'}

if ROLE=='catalog':
    @app.get('/network')
    def network():return load_network()
    @app.post('/validate')
    def validate(payload:dict=Body(...)):
        inputs(payload);return {'valid':True}
if ROLE=='forecast':
    @app.post('/forecast')
    def forecast(payload:dict=Body(default={})):
        import numpy as np
        net,cfg=inputs(payload);ps=net['plants'];ms={m['mine_id']:m for m in net['mines']}
        offers=np.array([min(ms[r['mine_id']]['coal_price_t']+cfg.coal_markup+r['freight_t']+cfg.rail_premium for r in net['routes'] if r['plant_id']==p['plant_id'])/p['mwh_per_t']+p['nonfuel_cost_mwh'] for p in ps])
        day=payload.get('day',0)
        if not isinstance(day,int) or not 0<=day<=365:raise HTTPException(422,'day must be integer 0..365')
        mean,sd=forecast_burn(cfg,ps,offers,day)
        return {'plant_ids':[p['plant_id'] for p in ps],'burn_t_day':mean.tolist(),'burn_sd_t_day':sd.tolist()}
if ROLE=='simulation':
    @app.post('/simulate')
    def run(payload:dict=Body(default={})):
        net,cfg=inputs(payload)
        try:r=simulate(net,cfg,payload.get('strategies'))
        except ValueError as e:raise HTTPException(422,str(e)) from e
        return {'summary':r['summary'],**{k:records(r[k]) for k in ['daily','stocks','prices','events']}}
    @app.post('/mechanisms')
    def mechanisms(payload:dict=Body(default={})):
        net,cfg=inputs(payload)
        if cfg.days>120:raise HTTPException(422,'Mechanism search limited to 120 days')
        return records(mechanism_search(net,cfg,max_budget_inr=float(payload.get('budget_inr',10_000_000))))
if ROLE=='game':
    @app.post('/convergence')
    def convergence(payload:dict=Body(default={})):
        net,cfg=inputs(payload)
        if cfg.days>60 or len(net['plants'])+len(net['mines'])>10:raise HTTPException(422,'Game service limited to 60 days and 10 sites')
        try:r=best_response_lab(net,cfg,rounds=int(payload.get('rounds',5)),mode=payload.get('mode','sequential'),adjustment_probability=float(payload.get('adjustment_probability',1)))
        except ValueError as e:raise HTTPException(422,str(e)) from e
        r['history']=records(r['history']);return r
