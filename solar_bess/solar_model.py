"""Solar-only BESS design LP. GW/GWh hourly AC boundary; money INR crore.
Copyright 2026 R. Gopalakrishnan. All rights reserved.
"""
import math
import numpy as np
from scipy.optimize import linprog
DEFAULT=dict(peak=330.,solar=500.,weather=1.,shift=20.,target=65.,mode='hourly',evening=0.,rte=88.,dod=90.,soh=80.,availability=95.,energy_cost=800.,power_cost=500.,wacc=9.,life=15.,om=2.,augmentation=1.,cycles=300.,charge_price=2.5,avoided_price=7.,rent=2.5,contract_hours=4.,variable_fee=.1)
BASE=np.array([.76,.73,.71,.70,.71,.75,.80,.84,.87,.90,.94,.97,.99,1,.99,.98,.97,.98,1,.99,.94,.89,.84,.79])
def validate(p):
 for k,v in p.items():
  if k=='mode':continue
  if not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError(f'{k} must be finite.')
 for k in ['peak','rte','dod','soh','availability','energy_cost','life','contract_hours']:
  if p[k]<=0:raise ValueError(f'{k} must be positive.')
 for k in ['solar','weather','shift','power_cost','wacc','om','augmentation','cycles','charge_price','avoided_price','rent','variable_fee']:
  if p[k]<0:raise ValueError(f'{k} cannot be negative.')
 for k in ['rte','dod','soh','availability','target','evening']:
  if not 0<=p[k]<=100:raise ValueError(f'{k} must be within 0-100.')
 if p['cycles']>365:raise ValueError('Operating days cannot exceed 365.')
 if p['mode'] not in ['hourly','energy']:raise ValueError('Mode must be hourly or energy.')
def profiles(p,custom=None):
 if custom is not None:
  if len(custom)!=24 or [int(r['hour']) for r in custom]!=list(range(24)):raise ValueError('CSV must contain hours 0-23 once, in order.')
  load=np.array([float(r['load_GW']) for r in custom]);solar=np.array([float(r['solar_GW']) for r in custom])
  if not np.isfinite(load).all() or not np.isfinite(solar).all() or min(load)<0 or min(solar)<0 or min(load[6:18])<=0:raise ValueError('Profiles must be finite, non-negative; daylight load must be positive.')
 else:
  load=p['peak']*BASE.copy()
  if p['shift']>min(load[18:24]):raise ValueError('Shift exceeds donor-hour demand.')
  load[18:24]-=p['shift'];load[10:16]+=p['shift']
  solar=np.array([p['solar']*.75*p['weather']*max(0,math.sin(math.pi*(h+.5-6)/12)) if 6<=h<18 else 0 for h in range(24)])
 return load,solar
def economics(p,P,E,dis,charge,usable):
 eta=math.sqrt(p['rte']/100);capex=E*p['energy_cost']+P*p['power_cost'];r=p['wacc']/100;n=p['life'];crf=r/(1-(1+r)**(-n)) if r else 1/n
 annual=dis*p['cycles'];charging=charge*p['cycles']*.1*p['charge_price'];fixed=capex*(crf+(p['om']+p['augmentation'])/100)
 contracted=max(P*p['availability']/100,usable*eta/p['contract_hours']);service_fixed=120*contracted*p['rent'];fee=annual*.1*p['variable_fee'];own=fixed+charging;service=service_fixed+charging+fee;value=annual*.1*p['avoided_price'];den=annual*.1
 return dict(capex_crore=capex,annual_discharge_GWh=annual,own_annual_crore=own,service_annual_crore=service,own_per_kWh=own/den if den else None,service_per_kWh=service/den if den else None,contract_GW=contracted,service_rent_ceiling=max(0,(fixed-fee)/(120*contracted)) if contracted else None,own_net_value_crore=value-own,service_net_value_crore=value-service,service_storage_only_per_kWh=(service_fixed+fee)/den if den else None,own_storage_only_per_kWh=fixed/den if den else None)
def solve(config=None,custom=None):
 p=DEFAULT|(config or {});validate(p);load,solar=profiles(p,custom);N=24;V=99;P=97;E=98;eta=math.sqrt(p['rte']/100);usable_factor=p['dod']/100*p['soh']/100;derate=p['availability']/100
 # columns direct[0:24], charge[24:48], discharge[48:72], SOC[72:97], P[97], E[98]
 ub=[];b=[];eq=[];beq=[]
 def inequality(items,rhs):
  row=np.zeros(V)
  for j,v in items:row[j]=v
  ub.append(row);b.append(rhs)
 for h in range(N):
  inequality([(h,1),(24+h,1)],solar[h]);inequality([(h,1),(48+h,1)],load[h]);inequality([(24+h,1),(P,-derate)],0);inequality([(48+h,1),(P,-derate)],0)
  if p['mode']=='hourly' and 6<=h<18:inequality([(h,-1),(48+h,-1)],-p['target']/100*load[h])
  if 18<=h<22:inequality([(h,-1),(48+h,-1)],-p['evening']/100*load[h])
  row=np.zeros(V);row[72+h+1]=1;row[72+h]=-1;row[24+h]=-eta;row[48+h]=1/eta;eq.append(row);beq.append(0)
 for h in range(25):inequality([(72+h,1),(E,-usable_factor)],0)
 if p['mode']=='energy':inequality([(h,-1) for h in range(6,18)]+[(48+h,-1) for h in range(6,18)],-p['target']/100*sum(load[6:18]))
 row=np.zeros(V);row[72]=1;row[96]=-1;eq.append(row);beq.append(0)
 objective=np.zeros(V);objective[P]=p['power_cost'];objective[E]=p['energy_cost']
 raw=linprog(objective,A_ub=ub,b_ub=b,A_eq=eq,b_eq=beq,bounds=(0,None),method='highs')
 summary=dict(parameters=p,feasible=bool(raw.success),solver_message=raw.message,day_load=float(sum(load[6:18])),daily_load=float(sum(load)),solar_generated=float(sum(solar)),direct_day_share=float(100*sum(np.minimum(load,solar)[6:18])/sum(load[6:18])),input_source='uploaded 24-hour profile' if custom is not None else 'synthetic representative day',solar_energy_lower_bound_GWh=float(p['target']/100*sum(load[6:18])+p['evening']/100*sum(load[18:22])))
 if not raw.success:
  summary.update(P_GW=None,E_GWh=None,message='No feasible cyclic solar-only dispatch meets this target. More BESS alone cannot fix an energy shortage. Change solar, weather, timing or target.',hourly=[dict(hour=h,load_GW=float(load[h]),solar_GW=float(solar[h])) for h in range(N)]);return summary
 # Lexicographic second pass: use as much solar as possible within the minimum CAPEX design.
 upper=raw.fun+max(1e-5,abs(raw.fun)*1e-8);ub2=list(ub)+[objective];b2=list(b)+[upper];secondary=np.zeros(V);secondary[:24]=-1;secondary[48:72]=-1;secondary[24:48]=1e-6
 refined=linprog(secondary,A_ub=ub2,b_ub=b2,A_eq=eq,b_eq=beq,bounds=(0,None),method='highs');x=refined.x if refined.success else raw.x
 x[np.abs(x)<1e-7]=0;direct=x[:24];charge=x[24:48];dis=x[48:72];soc=x[72:97];power=float(x[P]);energy=float(x[E]);usable=energy*usable_factor
 summary.update(P_GW=power,E_GWh=energy,usable_internal_GWh=usable,deliverable_GWh=usable*eta,optimal_capex_crore=float(raw.fun),day_share=float(100*sum((direct+dis)[6:18])/sum(load[6:18])),min_day_share=float(min(100*(direct+dis)[6:18]/load[6:18])),day_discharge=float(sum(dis[6:18])),evening_discharge=float(sum(dis[18:22])),curtailment=float(sum(solar-direct-charge)),losses=float(sum(charge)-sum(dis)),daily_discharge_GWh=float(sum(dis)),soc_cycle_error=float(abs(soc[0]-soc[-1])),max_simultaneous_GW=float(max(np.minimum(charge,dis))))
 summary.update(economics(p,power,energy,float(sum(dis)),float(sum(charge)),usable))
 summary['hourly']=[dict(hour=h,load_GW=float(load[h]),solar_GW=float(solar[h]),direct_GW=float(direct[h]),charge_GW=float(charge[h]),discharge_GW=float(dis[h]),other_GW=float(max(0,load[h]-direct[h]-dis[h])),curtailed_GW=float(max(0,solar[h]-direct[h]-charge[h])),soc_start_GWh=float(soc[h]),soc_end_GWh=float(soc[h+1])) for h in range(N)]
 return summary
