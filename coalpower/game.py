"""Finite strategy-policy game; measured regret, not a general equilibrium theorem."""
from dataclasses import replace
import numpy as np
import pandas as pd
from .engine import simulate


def best_response_lab(network,cfg,rounds=8,mode='sequential',adjustment_probability=1.,seeds=None):
    if mode not in ['sequential','simultaneous','random']:
        raise ValueError('Unknown update mode')
    if not 0<adjustment_probability<=1 or not 1<=rounds<=50:
        raise ValueError('Invalid adaptation controls')
    seeds=tuple(seeds or (cfg.seed,cfg.seed+1))
    actors=[m['mine_id'] for m in network['mines']]+['Railways']+[p['plant_id'] for p in network['plants']]
    keys=['coal:'+m['mine_id'] for m in network['mines']]+['rail']+['cover:'+p['plant_id'] for p in network['plants']]
    actions=[[0.,400.,800.] for _ in network['mines']]+[[0.,100.,300.]]+[[3.,7.,14.] for _ in network['plants']]
    profile=tuple(1 for _ in actors);cache={};rng=np.random.default_rng(cfg.seed)
    def evaluate(p):
        if p not in cache:
            strategies={k:actions[i][p[i]] for i,k in enumerate(keys)}
            s=[simulate(network,replace(cfg,seed=int(seed)),strategies)['summary'] for seed in seeds]
            cache[p]=({a:float(np.mean([x['agent_utilities_inr'][a] for x in s])) for a in actors},float(np.mean([x['social_cost_inr'] for x in s])))
        return cache[p]
    def response(p,i):
        base=evaluate(p)[0][actors[i]];best=p[i];value=base
        for j in range(len(actions[i])):
            trial=list(p);trial[i]=j;u=evaluate(tuple(trial))[0][actors[i]]
            if u>value+1e-5:best,value=j,u
        return best,max(0,value-base)
    history=[];seen={};status='iteration limit; no convergence established'
    for turn in range(rounds+1):
        utilities,cost=evaluate(profile)
        regrets=[response(profile,i)[1] for i in range(len(actors))]
        row={'round':turn,'max_regret_inr':max(regrets),'social_cost_inr':cost}
        row.update({k:actions[i][profile[i]] for i,k in enumerate(keys)})
        row.update({'regret:'+a:regrets[i] for i,a in enumerate(actors)})
        history.append(row)
        if max(regrets)<=1e-5:
            status='stable on tested action grid and scenario sample';break
        deterministic=mode!='random' and adjustment_probability==1
        if deterministic and profile in seen:
            status=f'cycle detected (period {turn-seen[profile]}); no convergence';break
        seen[profile]=turn
        if turn==rounds:break
        previous=profile
        if mode=='simultaneous':
            chosen=list(previous)
            for i in range(len(actors)):
                best,_=response(previous,i)
                if rng.random()<=adjustment_probability:chosen[i]=best
            profile=tuple(chosen)
        else:
            order=list(range(len(actors)))
            if mode=='random':rng.shuffle(order)
            for i in order:
                best,_=response(profile,i)
                if rng.random()<=adjustment_probability:
                    chosen=list(profile);chosen[i]=best;profile=tuple(chosen)
    return {'history':pd.DataFrame(history),'status':status,'evaluated_profiles':len(cache),'scenario_seeds':list(seeds),'final_utilities_inr':evaluate(profile)[0],
            'qualification':'Finite grid, fixed policies and sample-average payoffs only. A stable state is not a social optimum or a full stochastic-game equilibrium.'}


def counterexample(rounds=6):
    """Two stock-location coordinators prefer matching; simultaneous responses cycle."""
    a,b=0,1;rows=[]
    for t in range(rounds):
        rows.append({'round':t,'agent_A':a,'agent_B':b,'payoff_each':int(a==b)})
        a,b=b,a
    return pd.DataFrame(rows)
