import unittest,importlib,os
try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient=None
from coalpower.model import load_network

@unittest.skipIf(TestClient is None,'Optional service/dev dependencies are not installed')
class ServicesTests(unittest.TestCase):
    def client(self,role):
        os.environ['SERVICE_ROLE']=role
        import services.api as api
        return TestClient(importlib.reload(api).app)
    def test_catalog_and_validation(self):
        c=self.client('catalog');self.assertEqual(c.get('/health').status_code,200)
        self.assertIn('mines',c.get('/network').json())
        n=load_network();n['routes'][0]['plant_id']='absent'
        self.assertEqual(c.post('/validate',json={'network':n}).status_code,422)
    def test_forecast(self):
        r=self.client('forecast').post('/forecast',json={})
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['plant_ids']),3)
    def test_simulation_and_bad_strategy(self):
        c=self.client('simulation');r=c.post('/simulate',json={'config':{'days':3}})
        self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['daily']),3)
        self.assertEqual(c.post('/simulate',json={'strategies':{'rail':-1}}).status_code,422)
    def test_game(self):
        c=self.client('game');r=c.post('/convergence',json={'config':{'days':3},'rounds':1})
        self.assertEqual(r.status_code,200);self.assertIn('status',r.json())

if __name__=='__main__':unittest.main()
