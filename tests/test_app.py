"""Run explicitly: python -m unittest tests.test_app (Streamlit required)."""
import unittest
from pathlib import Path
try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest=None

@unittest.skipIf(AppTest is None,'Streamlit is not installed')
class AppSmoke(unittest.TestCase):
    def test_scenario_ui(self):
        app=Path(__file__).resolve().parents[1]/'app.py'
        at=AppTest.from_file(str(app),default_timeout=60).run()
        self.assertEqual(len(at.exception),0)
        next(b for b in at.button if b.label=='Run scenario').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.metric),4)

if __name__=='__main__':unittest.main()
