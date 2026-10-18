from pathlib import Path
import json
from solar_model import solve
cases=[('300 GW, hourly 65%',{'solar':300}),('450 GW, hourly 65%',{'solar':450}),('500 GW, energy 65%',{'mode':'energy'}),('500 GW, hourly 65%',{}),('500 GW, hourly 70%',{'target':70}),('600 GW, hourly 65%, evening 20%',{'solar':600,'evening':20}),('500 GW, cloudy',{'weather':.5})]
results=[dict(label=label,**solve(p)) for label,p in cases]
path=Path(__file__).parent/'data'/'scenario_results.json';path.write_text(json.dumps(results,indent=2))
print('Wrote',path)
