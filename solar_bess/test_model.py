import unittest,math
from solar_model import solve,profiles,DEFAULT,economics
class ModelTests(unittest.TestCase):
 def test_balances_and_capacity(self):
  for s in [300.,450.,500.,600.]:
   for m in ['hourly','energy']:
    for target in [60.,70.]:
     for evening in [0.,20.]:
      r=solve(dict(solar=s,mode=m,target=target,evening=evening))
      if not r['feasible']:continue
      self.assertLess(r['soc_cycle_error'],1e-5)
      self.assertGreaterEqual(r['day_share'],target-1e-5)
      if m=='hourly':self.assertGreaterEqual(r['min_day_share'],target-1e-5)
      for h in r['hourly']:
       self.assertAlmostEqual(h['solar_GW'],h['direct_GW']+h['charge_GW']+h['curtailed_GW'],places=5)
       self.assertAlmostEqual(h['load_GW'],h['direct_GW']+h['discharge_GW']+h['other_GW'],places=5)
       self.assertLessEqual(h['soc_end_GWh'],r['usable_internal_GWh']+1e-5)
       self.assertLessEqual(max(h['charge_GW'],h['discharge_GW']),r['P_GW']*.95+1e-5)
       if 18<=h['hour']<22:self.assertGreaterEqual(h['direct_GW']+h['discharge_GW'],evening/100*h['load_GW']-1e-5)
      self.assertLess(r['max_simultaneous_GW'],1e-4)
 def test_solar_shortage(self):self.assertFalse(solve({'solar':300})['feasible'])
 def test_energy_no_battery(self):self.assertLess(solve({'mode':'energy'})['E_GWh'],1e-5)
 def test_shift_conservation(self):
  a,_=profiles(DEFAULT|{'shift':0});b,_=profiles(DEFAULT|{'shift':30});self.assertAlmostEqual(sum(a),sum(b));self.assertAlmostEqual(sum(b[10:16])-sum(a[10:16]),180)
 def test_weather_stress(self):self.assertFalse(solve({'weather':.5})['feasible'])
 def test_service_units(self):
  p=DEFAULT;z=economics(p,1,.5,1,1/.88,.5*.9*.8);self.assertAlmostEqual(z['service_annual_crore'],z['contract_GW']*2.5*120+300/.88*.1*2.5+300*.1*.1)
 def test_more_solar_not_higher_min_capex(self):
  self.assertLessEqual(solve({'solar':600})['optimal_capex_crore'],solve({'solar':500})['optimal_capex_crore']+1e-4)
 def test_invalid(self):
  for p in [{'rte':0},{'rte':101},{'cycles':400},{'shift':1000},{'solar':float('nan')}]:self.assertRaises(ValueError,solve,p)
 def test_custom_profile(self):
  r=solve();custom=[{'hour':h['hour'],'load_GW':h['load_GW'],'solar_GW':h['solar_GW']} for h in r['hourly']];q=solve({},custom);self.assertAlmostEqual(q['E_GWh'],r['E_GWh'],places=4)
 def test_zero_solar_zero_target(self):
  r=solve({'solar':0,'target':0});self.assertTrue(r['feasible']);self.assertAlmostEqual(r['E_GWh'],0)
if __name__=='__main__':unittest.main()
