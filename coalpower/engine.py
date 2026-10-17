"""Daily, discrete-rake, multi-location engine with hourly pooled-grid dispatch.
No perfect-foresight or equilibrium optimality is claimed. All money is INR.
"""
from dataclasses import asdict, replace
import hashlib,json
from pathlib import Path
from statistics import NormalDist
import numpy as np
import pandas as pd
from .model import Config, validate_network


def merit_dispatch(net_mw, plants, offers, fuel=None):
    """Dispatch unconstrained pooled grid; return hourly energy, load shed, price."""
    net=np.maximum(np.asarray(net_mw,dtype=float),0)
    energy=np.zeros((len(plants),len(net)))
    left=net.copy()
    for i in np.argsort(offers,kind='stable'):
        cap=plants[i]['capacity_mw']
        for h in range(len(net)):
            available=cap if fuel is None else min(cap,max(0,fuel[i])*plants[i]['mwh_per_t'])
            e=min(left[h],available)
            energy[i,h]=e;left[h]-=e
            if fuel is not None:
                fuel[i]-=e/plants[i]['mwh_per_t']
    prices=np.max(np.where(energy>1e-8,np.asarray(offers)[:,None],0),axis=0)
    return energy,left,prices


def forecast_burn(cfg,plants,offers,day):
    """Forecast distribution uses known seasonality, never future realized shocks."""
    h=np.arange(24)
    demand=cfg.demand_mw*(1+.10*np.sin(2*np.pi*day/90))*(1+.14*np.cos((h-20)*2*np.pi/24))
    solar=.85*cfg.solar_mw*np.maximum(0,np.sin((h-6)*np.pi/12))
    mean_net=np.maximum(0,demand-solar-cfg.wind_mw*cfg.wind_cf)
    # Fixed quadrature of uncertain residual demand preserves peaker dispatch risk.
    sigma=np.sqrt((cfg.demand_mw*cfg.demand_volatility)**2+
                  (cfg.renewable_volatility*(cfg.solar_mw/3+cfg.wind_mw*cfg.wind_cf))**2)
    zs=np.array([-2.,-1.3,-.7,0.,.7,1.3,2.])
    weights=np.array([.025,.10,.225,.30,.225,.10,.025])
    burns=[]
    for z in zs:
        e,_,_=merit_dispatch(np.maximum(0,mean_net+z*sigma),plants,offers)
        burns.append(e.sum(axis=1)/np.array([p['mwh_per_t'] for p in plants]))
    burns=np.array(burns)
    mean=np.sum(weights[:,None]*burns,axis=0)
    burn_sd=np.sqrt(np.sum(weights[:,None]*(burns-mean)**2,axis=0))
    return mean,np.maximum(mean*.03,burn_sd)



def stock_target(mean,sd,lead,cfg,price,storage,mwh_per_t,cover=None):
    """Cost-sensitive quantile heuristic; bounded, expressly not global optimum."""
    cover=cfg.plant_cover_days if cover is None else cover
    horizon=max(1,lead+1)
    overage=max(.01,(price*cfg.annual_carry_rate/365+storage)*horizon)
    underage=max(1,cfg.performance_penalty_mwh*mwh_per_t)
    if cfg.policy=='coordinated':
        underage += cfg.availability_payment*horizon
    critical=np.clip(underage/(underage+overage),.5,.995)
    quantile=min(cfg.safety_quantile,critical)
    z=NormalDist().inv_cdf(max(.5,min(.995,quantile)))
    if cfg.policy=='static':
        return mean*cover
    # Working protection plus cost-sensitive safety; prebuild transport-shock protection.
    working=mean*horizon
    safety=z*sd*np.sqrt(horizon)
    seasonal=mean*cfg.shock_probability*cfg.shock_severity*lead
    raw=working+safety+seasonal+cfg.rake_tonnes
    downstream=(1-cfg.pithead_share)*max(0,raw-working)
    return min(max(mean*cover,cfg.rake_tonnes if sd>0 else 0),working+downstream)


def simulate(network,cfg=None,strategies=None):
    cfg=cfg or Config();cfg.validate();validate_network(network)
    strategies=strategies or {}
    import math
    allowed={'rail'}|{'coal:'+m['mine_id'] for m in network['mines']}|{'cover:'+p['plant_id'] for p in network['plants']}
    if not isinstance(strategies,dict) or set(strategies)-allowed:
        raise ValueError('Unknown strategy keys')
    for key,value in strategies.items():
        if not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            raise ValueError('Strategy values must be finite and nonnegative')
    mines=network['mines'];plants=network['plants'];routes=network['routes']
    mi={x['mine_id']:i for i,x in enumerate(mines)};pi={x['plant_id']:i for i,x in enumerate(plants)}
    mine_stock=np.array([m['initial_stock_t'] for m in mines],dtype=float)
    plant_stock=np.array([p['initial_stock_t'] for p in plants],dtype=float)
    mine_prices=np.array([m['coal_price_t']+strategies.get('coal:'+m['mine_id'],cfg.coal_markup) for m in mines])
    ref_cost=float(np.mean([m['mining_cost_t'] for m in mines]))
    initial_mass=float(mine_stock.sum()+plant_stock.sum())
    # Accounting uses book values for private capital charges, common resource value socially.
    book=np.array([min(mine_prices[mi[r['mine_id']]]+r['freight_t'] for r in routes if r['plant_id']==p['plant_id']) for p in plants])
    accounts={m['mine_id']:0. for m in mines}|{p['plant_id']:0. for p in plants}|{'Railways':0.}
    pipeline=[];fleet=[];events=[];daily=[];stock_rows=[];price_rows=[]
    produced=burned=discarded=0.;resource=private_carry=shortage_loss=reserve_spend=0.
    prev_orders=0.;previous_capacity=sum(c['rakes_per_day'] for c in network['corridors'])
    rng=np.random.default_rng(cfg.seed)
    # Fixed number of exogenous draws per day; route delays share common corridor shock.
    shocks=rng.random((cfg.days,5));normals=rng.normal(size=(cfg.days,4))
    private_rail_premium=strategies.get('rail',cfg.rail_premium)
    for t in range(cfg.days):
        weather=normals[t,0]
        disrupted=shocks[t,0]<cfg.shock_probability
        factor=1-cfg.shock_severity if disrupted else 1.
        fleet=[release for release in fleet if release>t]
        arrivals=[s for s in pipeline if s['arrival_day']<=t]
        for s in arrivals:
            i=pi[s['plant_id']];qty=s['tonnes'];space=plants[i]['capacity_t']-plant_stock[i]
            # Storage space reserved at loading, so overflow indicates a modeling defect.
            if qty>space+1e-5:
                raise AssertionError('Reserved plant storage exceeded')
            book[i]=(book[i]*plant_stock[i]+s['book_value_t']*qty)/max(1,plant_stock[i]+qty)
            plant_stock[i]+=qty
            events.append({'day':t,'event':'arrived',**s})
        pipeline=[s for s in pipeline if s['arrival_day']>t]
        scarcity=np.maximum(0,1-mine_stock/np.maximum(1,np.array([m['production_tpd']*max(1,cfg.mine_cover_days) for m in mines])))
        desired=np.array([m['coal_price_t']+strategies.get('coal:'+m['mine_id'],cfg.coal_markup) for m in mines])+300*scarcity
        mine_prices=(1-cfg.price_smoothing)*mine_prices+cfg.price_smoothing*desired
        congestion=max(0,prev_orders/max(1,previous_capacity*cfg.rake_tonnes)-1)
        rail_signal=private_rail_premium+cfg.congestion_gain*congestion
        delivered=np.array([min(mine_prices[mi[r['mine_id']]]+r['freight_t']+rail_signal for r in routes if r['plant_id']==p['plant_id']) for p in plants])
        offers=delivered/np.array([p['mwh_per_t'] for p in plants])+np.array([p['nonfuel_cost_mwh'] for p in plants])
        mean,sd=forecast_burn(cfg,plants,offers,t)
        total_mean=float(mean.sum())
        # Upstream reserve reacts to net thermal requirement, not gross electricity demand.
        production=[]
        for j,m in enumerate(mines):
            share=m['production_tpd']/sum(x['production_tpd'] for x in mines)
            target=share*total_mean*cfg.mine_cover_days + cfg.pithead_share*share*float(sd.sum())*2
            q=min(m['production_tpd']*factor,max(0,target+share*total_mean-mine_stock[j]),m['capacity_t']-mine_stock[j])
            mine_stock[j]+=q;produced+=q;production.append(q)
            cost=q*m['mining_cost_t'];resource+=cost;accounts[m['mine_id']]-=cost
        requests=[];targets=[]
        for i,p in enumerate(plants):
            available_routes=[r for r in routes if r['plant_id']==p['plant_id']]
            lead=int(np.ceil(np.quantile([r['lead_days'] for r in available_routes],cfg.safety_quantile)))
            if cfg.shock_probability>1-cfg.safety_quantile:
                lead+=int(np.ceil(cfg.shock_severity*3))
            target=stock_target(mean[i],sd[i],lead,cfg,delivered[i],p['storage_cost_t_day'],p['mwh_per_t'],strategies.get('cover:'+p['plant_id']))
            inbound=sum(s['tonnes'] for s in pipeline if s['plant_id']==p['plant_id'])
            dated_inbound=sum(s['tonnes'] for s in pipeline if s['plant_id']==p['plant_id'] and s['arrival_day']<=t+lead+1)
            need=max(0,min(target-plant_stock[i]-dated_inbound,p['capacity_t']-plant_stock[i]-inbound))
            targets.append(target)
            # Quantity rounded down to complete rakes; position counts every committed tonne once.
            requests.append(int(need//cfg.rake_tonnes))
        prev_orders=sum(requests)*cfg.rake_tonnes
        capacities={c['corridor_id']:int(c['rakes_per_day']*factor) for c in network['corridors']}
        previous_capacity=sum(capacities.values())
        route_used={r['route_id']:0 for r in routes}
        # Urgency adjusted by arrival lead time; fixed index tie-break for reproducibility.
        urgency=[plant_stock[i]/max(1,mean[i])-min(r['lead_days'] for r in routes if r['plant_id']==p['plant_id']) for i,p in enumerate(plants)]
        loaded=0
        for i in sorted(range(len(plants)),key=lambda k:urgency[k]):
            p=plants[i]
            alternatives=sorted([r for r in routes if r['plant_id']==p['plant_id']],key=lambda r:mine_prices[mi[r['mine_id']]]+r['freight_t']+rail_signal)
            for _ in range(requests[i]):
                if len(fleet)>=cfg.fleet_rakes:break
                chosen=next((r for r in alternatives if mine_stock[mi[r['mine_id']]]+1e-8>=cfg.rake_tonnes and capacities[r['corridor_id']]>0 and route_used[r['route_id']]<int(r['rakes_per_day'])),None)
                if chosen is None:break
                r=chosen;j=mi[r['mine_id']];q=cfg.rake_tonnes
                delay=int(np.ceil(cfg.shock_severity*3)) if disrupted else 0
                arrival=t+int(r['lead_days'])+delay
                cargo={'consignment_id':f'{t}-{loaded}','mine_id':r['mine_id'],'plant_id':p['plant_id'],'route_id':r['route_id'],'tonnes':q,'loaded_day':t,'arrival_day':arrival,'book_value_t':mine_prices[j]+r['freight_t']+rail_signal}
                pipeline.append(cargo);fleet.append(arrival+cfg.empty_return_days+1)
                events.append({'day':t,'event':'loaded',**cargo})
                mine_stock[j]-=q;capacities[r['corridor_id']]-=1;route_used[r['route_id']]+=1;loaded+=1
                coal_bill=q*mine_prices[j];rail_bill=q*(r['freight_t']+rail_signal)
                accounts[r['mine_id']]+=coal_bill;accounts['Railways']+=rail_bill-q*r['real_transport_cost_t'];accounts[p['plant_id']]-=coal_bill+rail_bill
                resource+=q*r['real_transport_cost_t']
        h=np.arange(24)
        gross=cfg.demand_mw*(1+.10*np.sin(2*np.pi*t/90))*(1+.14*np.cos((h-20)*2*np.pi/24))*max(.3,1+cfg.demand_volatility*(.65*weather+.76*normals[t,1]))
        solar=cfg.solar_mw*np.maximum(0,np.sin((h-6)*np.pi/12))*np.clip(.85-cfg.renewable_volatility*weather,0,1)
        wind=cfg.wind_mw*np.clip(cfg.wind_cf*(1+cfg.renewable_volatility*normals[t,2]),0,1)
        net=np.maximum(0,gross-solar-wind)
        desired_energy,_,_=merit_dispatch(net,plants,offers)
        energy,lost,market=merit_dispatch(net,plants,offers,plant_stock)
        market=np.where(lost>1e-6,cfg.electricity_price_cap,np.minimum(market,cfg.electricity_price_cap))
        e_by=energy.sum(axis=1);burn=e_by/np.array([p['mwh_per_t'] for p in plants]);burned+=float(burn.sum())
        lost_cost=float(lost.sum())*cfg.value_lost_load_mwh;resource+=lost_cost;shortage_loss+=lost_cost
        day_carry=0
        for j,m in enumerate(mines):
            carry=mine_stock[j]*(m['storage_cost_t_day']+cfg.annual_carry_rate*m['mining_cost_t']/365)
            accounts[m['mine_id']]-=carry;resource+=carry;day_carry+=carry
            stock_rows.append({'day':t,'node':m['mine_id'],'location':'pithead','stock_t':mine_stock[j],'target_t':None})
        for i,p in enumerate(plants):
            inbound=sum(s['tonnes'] for s in pipeline if s['plant_id']==p['plant_id'])
            carry=plant_stock[i]*(p['storage_cost_t_day']+cfg.annual_carry_rate*book[i]/365)
            transit_carry=sum(s['tonnes']*s['book_value_t']*cfg.annual_carry_rate/365 for s in pipeline if s['plant_id']==p['plant_id'])
            day_carry+=carry+transit_carry;private_carry+=carry+transit_carry
            real_carry=plant_stock[i]*(p['storage_cost_t_day']+ref_cost*cfg.annual_carry_rate/365)+inbound*ref_cost*cfg.annual_carry_rate/365
            nonfuel=e_by[i]*p['nonfuel_cost_mwh'];resource+=real_carry+nonfuel+e_by[i]*cfg.carbon_cost_mwh
            # Payment only for on-hand stock up to model target; no transit double credit.
            reserve=cfg.availability_payment*min(plant_stock[i],targets[i]) if cfg.policy=='coordinated' else 0.
            reserve_spend+=reserve
            penalty=cfg.performance_penalty_mwh*max(0,desired_energy[i].sum()-e_by[i])
            accounts[p['plant_id']]+=float((energy[i]*market).sum())+reserve-nonfuel-carry-transit_carry-penalty
            stock_rows.append({'day':t,'node':p['plant_id'],'location':'plant','stock_t':max(0,plant_stock[i]),'target_t':targets[i],'in_transit_t':inbound,'burn_t':burn[i],'generation_mwh':e_by[i]})
        mass=float(mine_stock.sum()+plant_stock.sum()+sum(s['tonnes'] for s in pipeline))
        error=initial_mass+produced-burned-discarded-mass
        if abs(error)>1e-4 or min(plant_stock)<-1e-5 or min(mine_stock)<-1e-5:
            raise AssertionError(f'Coal mass conservation failure: {error}')
        for j,m in enumerate(mines):
            price_rows.append({'day':t,'agent':m['mine_id'],'coal_offer_t':mine_prices[j],'rail_signal_t':rail_signal})
        daily.append({'day':t,'gross_demand_mwh':float(gross.sum()),'renewable_available_mwh':float(solar.sum()+wind*24),'thermal_requirement_mwh':float(net.sum()),'generation_mwh':float(e_by.sum()),'unserved_mwh':float(lost.sum()),'pithead_t':float(mine_stock.sum()),'plant_t':float(plant_stock.sum()),'in_transit_t':sum(s['tonnes'] for s in pipeline),'rakes_loaded':loaded,'rakes_busy':len(fleet),'production_t':sum(production),'burn_t':float(burn.sum()),'private_carry_inr':day_carry,'mass_error_t':error,'system_cost_cumulative_inr':resource})
    final_mass=float(mine_stock.sum()+plant_stock.sum()+sum(s['tonnes'] for s in pipeline))
    # Common, explicit endowment/salvage convention for comparison (not an estimated market value).
    adjusted=resource+(initial_mass-final_mass)*ref_cost
    final_private=accounts.copy()
    for i,p in enumerate(plants):
        remaining=plant_stock[i]*book[i]+sum(s['tonnes']*s['book_value_t'] for s in pipeline if s['plant_id']==p['plant_id'])
        initial=p['initial_stock_t']*min((mines[mi[r['mine_id']]]['coal_price_t']+strategies.get('coal:'+r['mine_id'],cfg.coal_markup)+r['freight_t']) for r in routes if r['plant_id']==p['plant_id'])
        final_private[p['plant_id']]+=remaining-initial
    for j,m in enumerate(mines):
        final_private[m['mine_id']]+=(mine_stock[j]-m['initial_stock_t'])*m['mining_cost_t']
    summary={'social_cost_inr':adjusted,'unadjusted_resource_cost_inr':resource,'terminal_adjustment_inr':(initial_mass-final_mass)*ref_cost,'unserved_mwh':sum(x['unserved_mwh'] for x in daily),'generation_mwh':sum(x['generation_mwh'] for x in daily),'private_plant_and_pipeline_carry_inr':private_carry,'availability_payments_inr':reserve_spend,'final_inventory_t':final_mass,'mass_error_max_t':max(abs(x['mass_error_t']) for x in daily),'agent_utilities_inr':final_private,'synthetic':True,'engine_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'network_sha256':hashlib.sha256(json.dumps(network,sort_keys=True).encode()).hexdigest(),'config':asdict(cfg)}
    return {'summary':summary,'daily':pd.DataFrame(daily),'stocks':pd.DataFrame(stock_rows),'prices':pd.DataFrame(price_rows),'events':pd.DataFrame(events)}


def compare_policies(network,cfg,seeds=(11,29,47)):
    rows=[]
    for policy in ['static','dynamic','coordinated']:
        for seed in seeds:
            s=simulate(network,replace(cfg,policy=policy,seed=int(seed)))['summary']
            rows.append({'policy':policy,'seed':seed,**{k:v for k,v in s.items() if isinstance(v,(float,int)) and not isinstance(v,bool)}})
    return pd.DataFrame(rows)


def mechanism_search(network,cfg,seeds=(11,29),max_budget_inr=10_000_000):
    """Finite SAA candidate search; best tested heuristic, not globally optimal pricing."""
    rows=[]
    for share in [.15,.5,.85]:
        for payment in [0.,2.,5.]:
            for premium in [0.,100.]:
                candidate=replace(cfg,policy='coordinated',pithead_share=share,availability_payment=payment,rail_premium=premium)
                ss=[simulate(network,replace(candidate,seed=int(seed)))['summary'] for seed in seeds]
                rows.append({'pithead_share':share,'availability_payment':payment,'rail_premium':premium,'mean_social_cost_inr':float(np.mean([s['social_cost_inr'] for s in ss])),'mean_unserved_mwh':float(np.mean([s['unserved_mwh'] for s in ss])),'mean_payment_inr':float(np.mean([s['availability_payments_inr'] for s in ss]))})
    frame=pd.DataFrame(rows)
    frame['within_budget']=frame.mean_payment_inr<=max_budget_inr
    return frame.sort_values(['within_budget','mean_social_cost_inr'],ascending=[False,True]).reset_index(drop=True)
