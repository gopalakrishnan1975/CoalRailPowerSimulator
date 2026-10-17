import unittest,copy
from dataclasses import replace
import numpy as np
from coalpower.model import Config,load_network,validate_network
from coalpower.engine import simulate,stock_target,compare_policies
from coalpower.game import best_response_lab,counterexample

class PhysicalTests(unittest.TestCase):
    def setUp(self):self.net=load_network();self.cfg=Config(days=25)
    def test_mass_and_fleet(self):
        r=simulate(self.net,self.cfg);d=r['daily']
        self.assertLess(d.mass_error_t.abs().max(),1e-5)
        self.assertLessEqual(d.rakes_busy.max(),self.cfg.fleet_rakes)
        self.assertGreaterEqual(r['stocks'].stock_t.min(),-1e-6)
        self.assertTrue(np.allclose(d.generation_mwh+d.unserved_mwh,d.thermal_requirement_mwh))
    def test_reproducibility(self):
        self.assertTrue(simulate(self.net,self.cfg)['daily'].equals(simulate(self.net,self.cfg)['daily']))
    def test_renewables_displace_thermal_requirement(self):
        lo=simulate(self.net,replace(self.cfg,solar_mw=0,wind_mw=0))
        hi=simulate(self.net,replace(self.cfg,solar_mw=2500,wind_mw=1200))
        self.assertLess(hi['daily'].thermal_requirement_mwh.sum(),lo['daily'].thermal_requirement_mwh.sum())
    def test_arrival_time(self):
        e=simulate(self.net,self.cfg)['events'];loads=e[e.event=='loaded'];arrivals=e[e.event=='arrived']
        self.assertTrue((loads.arrival_day>loads.loaded_day).all())
        self.assertTrue((arrivals.day>=arrivals.arrival_day).all())
        self.assertEqual(len(loads.consignment_id.unique()),len(loads))
    def test_storage_capacity(self):
        net=copy.deepcopy(self.net)
        for p in net['plants']:p['capacity_t']=p['initial_stock_t']+1000
        r=simulate(net,self.cfg)
        for p in net['plants']:
            self.assertLessEqual(r['stocks'].loc[r['stocks'].node==p['plant_id'],'stock_t'].max(),p['capacity_t']+1e-5)
    def test_bad_references_and_nan(self):
        net=copy.deepcopy(self.net);net['routes'][0]['mine_id']='missing'
        with self.assertRaises(ValueError):validate_network(net)
        with self.assertRaises(ValueError):replace(self.cfg,annual_carry_rate=float('nan')).validate()
    def test_carrying_cost_changes_target(self):
        low=stock_target(100,80,5,replace(self.cfg,annual_carry_rate=0,performance_penalty_mwh=5,safety_quantile=.995),5000,0,2)
        high=stock_target(100,80,5,replace(self.cfg,annual_carry_rate=.4,performance_penalty_mwh=5,safety_quantile=.995),5000,0,2)
        self.assertLess(high,low)
    def test_complete_renewable_cover(self):
        r=simulate(self.net,replace(self.cfg,days=5,solar_mw=0,wind_mw=10000,wind_cf=1,renewable_volatility=0))
        self.assertEqual(r['summary']['generation_mwh'],0)
        self.assertEqual(r['summary']['unserved_mwh'],0)
    def test_closed_corridors(self):
        net=copy.deepcopy(self.net)
        for c in net['corridors']:c['rakes_per_day']=0
        self.assertEqual(simulate(net,self.cfg)['daily'].rakes_loaded.sum(),0)
    def test_zero_penalty_allowed(self):
        simulate(self.net,replace(self.cfg,performance_penalty_mwh=0,availability_payment=0))
    def test_policy_seeds(self):
        d=compare_policies(self.net,replace(self.cfg,days=3),seeds=(1,2))
        self.assertEqual(len(d),6);self.assertEqual(set(d.seed),{1,2})
    def test_toy_cycle(self):
        self.assertEqual(counterexample().agent_A.tolist(),[0,1,0,1,0,1])
    def test_game_regret(self):
        r=best_response_lab(self.net,replace(self.cfg,days=3),rounds=1,seeds=(1,))
        self.assertGreater(r['evaluated_profiles'],1)
        self.assertTrue((r['history'].max_regret_inr>=0).all())

if __name__=='__main__':unittest.main()
