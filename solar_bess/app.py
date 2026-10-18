"""Streamlit entrypoint; deploy solar_bess/app.py from the repository root."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pandas as pd
import streamlit as st
from solar_model import solve,DEFAULT
st.set_page_config(page_title='Solar, Demand & BESS Policy Lab',page_icon='☀️',layout='wide')
st.title('Solar, Demand & BESS Policy Lab')
st.caption('R. Gopalakrishnan · Optimised representative-day scenarios · Synthetic defaults, not an official national forecast')
st.markdown('Compare a **share of total daytime energy** with a **minimum share in every daylight hour**. Size storage, shift flexible consumption and test ownership against storage as a service.')
@st.cache_data(show_spinner=False)
def run(p,custom=None):return solve(p,custom)
with st.sidebar:
 st.header('Supply and service target')
 mode_label=st.selectbox('Daytime target definition',['Every daylight hour','Integrated daytime energy'])
 p=dict(DEFAULT);p['mode']='hourly' if mode_label=='Every daylight hour' else 'energy'
 for k,label,lo,hi,step in [('peak','Unshifted demand peak (GW)',100.,500.,5.),('solar','Solar nameplate capacity (GW)',0.,1000.,10.),('target','Daytime solar-backed target (%)',0.,100.,1.),('evening','Evening solar-backed floor (%)',0.,100.,5.)]:p[k]=st.slider(label,lo,hi,float(DEFAULT[k]),step)
 p['weather']=st.slider('Solar weather multiplier',0.,1.2,1.,.05)
 st.caption('Windows: daytime 06–18; evening 18–22 IST. All plotted powers are one-hour averages.')
 st.header('Demand flexibility')
 sector_mode=st.checkbox('Build shift from sectors',False)
 if sector_mode:
  amounts={}
  for label,v in [('Agricultural pumping',40.),('EV charging',20.),('Building pre-cooling',20.),('Industrial processes',20.),('Municipal water pumping',10.),('Office schedule response',10.)]:amounts[label]=st.number_input(label+' (GWh/day)',0.,100.,v,5.)
  participation=st.slider('Fraction actually shifted (%)',0.,100.,100.,5.)
  p['shift']=sum(amounts.values())*participation/100/6
 else:p['shift']=st.slider('Evening → midday shift (GW)',0.,60.,20.,5.)
 st.caption('Moves the selected GW out of each hour 18–24 into 10–16. The sector amounts describe delivered energy shifts, not measured flexibility forecasts.')
 peak_tariff=st.number_input('Illustrative peak tariff (INR/kWh)',0.,30.,9.6,.1)
 solar_tariff=st.number_input('Illustrative solar tariff (INR/kWh)',0.,30.,6.4,.1)
 st.header('Battery assumptions')
 for k,label,lo,hi,step in [('rte','Round-trip efficiency (%)',50.,100.,1.),('dod','Depth of discharge (%)',40.,100.,1.),('soh','End-of-life retained energy (%)',50.,100.,1.),('availability','Power derating (%)',70.,100.,1.)]:p[k]=st.slider(label,lo,hi,float(DEFAULT[k]),step)
 with st.expander('Economics: editable assumptions'):
  labels={'energy_cost':'Energy CAPEX (INR crore/GWh)','power_cost':'Power CAPEX (INR crore/GW)','wacc':'Real discount rate (%)','life':'Economic life (years)','om':'Annual O&M (% CAPEX)','augmentation':'Annual augmentation reserve (% CAPEX)','cycles':'Representative operating days/year','charge_price':'Charging electricity (INR/kWh)','avoided_price':'Avoided electricity purchase (INR/kWh)','rent':'Service rent (INR lakh/MW/month)','contract_hours':'Guaranteed AC service duration (hours)','variable_fee':'Service throughput fee (INR/kWh)'}
  for k,label in labels.items():p[k]=st.number_input(label,min_value=.1 if k in ['energy_cost','life','contract_hours'] else 0.,max_value=365. if k=='cycles' else None,value=float(DEFAULT[k]),step=.1)
 uploaded=st.file_uploader('Custom 24-hour CSV',type='csv',help='hour,load_GW,solar_GW; hours 0–23 exactly once in order. Replaces synthetic load, solar, weather and shifting.')
custom=None
if uploaded:
 try:
  df=pd.read_csv(uploaded);custom=df.to_dict('records')
 except Exception as exc:st.error('Cannot read CSV: '+str(exc));st.stop()
 st.info('Imported profiles are used as supplied. Synthetic supply, demand, weather and shift controls are bypassed; tariff-shift savings are not inferred for imports.')
try:r=run(p,custom)
except (ValueError,KeyError,TypeError) as exc:st.error(str(exc));st.stop()
tabs=st.tabs(['Dispatch & storage','Ownership vs service','Scenarios & data','Method & policy'])
with tabs[0]:
 if not r['feasible']:
  st.warning(r['message']);st.write('Necessary energy lower bound before losses:',round(r['solar_energy_lower_bound_GWh'],1),'GWh/day; available solar generation:',round(r['solar_generated'],1),'GWh/day.')
  st.caption('The bound is necessary, not sufficient: chronological timing and losses also matter.')
 else:
  c=st.columns(4)
  for col,label,value in zip(c,['BESS nameplate power','BESS nameplate energy','Daytime solar-backed energy','Lowest daylight hourly share'],[f"{r['P_GW']:.1f} GW",f"{r['E_GWh']:.1f} GWh",f"{r['day_share']:.1f}%",f"{r['min_day_share']:.1f}%"]):col.metric(label,value)
  st.caption(f"End-of-life usable internal energy: {r['usable_internal_GWh']:.1f} GWh; AC deliverable energy: {r['deliverable_GWh']:.1f} GWh. This is a minimum-capital-cost battery design at the selected fixed solar capacity, not a national adequacy estimate.")
 df=pd.DataFrame(r['hourly']).set_index('hour');st.subheader('Hourly power balance (GW)');st.line_chart(df[[k for k in ['load_GW','solar_GW','direct_GW','charge_GW','discharge_GW','other_GW'] if k in df]])
 if r['feasible']:
  st.subheader('Internal state of charge (GWh)');st.line_chart(df[['soc_start_GWh','soc_end_GWh']]);a,b,c=st.columns(3);a.metric('Solar curtailed',f"{r['curtailment']:.1f} GWh/day");b.metric('Storage losses',f"{r['losses']:.1f} GWh/day");c.metric('Direct daytime share without BESS',f"{r['direct_day_share']:.1f}%")
 if custom is None:st.info(f"Demand shift: {6*p['shift']:.1f} GWh/day. Illustrative bill saving from the stated tariff difference: INR {6*p['shift']*.1*(peak_tariff-solar_tariff):,.1f} crore/day, before programme costs, constraints and rebound. These are customer-bill transfers, not automatically net system savings.")
with tabs[1]:
 st.subheader('Compare the same delivered service')
 st.caption('Illustrative costs, not market quotes. Charging is separately included. Direct solar generation costs, network charges, subsidies, taxes and demand-response costs are excluded.')
 if not r['feasible']:st.write('Resolve physical feasibility first.')
 elif r['P_GW']<1e-5:st.success('No BESS is required for this target on this day. Buying storage service is unnecessary for this objective.')
 else:
  st.dataframe(pd.DataFrame({'Own':[r['own_annual_crore'],r['own_storage_only_per_kWh'],r['own_per_kWh'],r['own_net_value_crore']],'Service':[r['service_annual_crore'],r['service_storage_only_per_kWh'],r['service_per_kWh'],r['service_net_value_crore']]},index=['Annual battery + charging cost (INR crore)','Storage-only cost (INR/kWh delivered)','Including charging (INR/kWh delivered)','Avoided purchases less total cost (INR crore/year)']).round(2),width='stretch')
  st.write(f"Ownership CAPEX: INR {r['capex_crore']:,.0f} crore. Contracted service block: {r['contract_GW']:.1f} GW × {p['contract_hours']:g} guaranteed AC hours. Ownership-equivalent service rent: INR {r['service_rent_ceiling']:.2f} lakh/MW/month at the entered throughput fee.")
  st.warning('A lower quote than ownership does not prove provider viability. A provider with the same CAPEX and financing assumptions needs the equivalent rent above unless other contracted revenue, lower costs or explicit support closes the gap. A cheaper option may still cost more than avoided purchases.')
  contract=['Guaranteed AC MW and MWh at end of life','Dispatch rights, cycles and throughput envelope','Efficiency and charging-energy responsibility','Availability during the contracted hours','Augmentation, fire protection, insurance and recycling','Connection charges, payment security and non-delivery remedies','No double commitment of reserved capacity to ancillary services']
  st.markdown('\n'.join('- '+x for x in contract))
with tabs[2]:
 st.subheader('Solar capacity sensitivity')
 if custom is None:
  cases=[]
  for capacity in [300.,400.,450.,500.,600.,700.]:
   q=run(p|{'solar':capacity});cases.append({'Solar GW':capacity,'Feasible':q['feasible'],'BESS GW':q.get('P_GW'),'BESS GWh':q.get('E_GWh'),'Day share %':q.get('day_share')})
  st.dataframe(pd.DataFrame(cases).round(2),width='stretch')
 else:st.write('Synthetic capacity sweep disabled for imported profiles.')
 st.dataframe(df.round(3),width='stretch')
 st.download_button('Export hourly CSV',df.to_csv(),'solar_bess_hourly.csv','text/csv')
 st.download_button('Export scenario JSON',json.dumps(r,indent=2),'solar_bess_scenario.json','application/json')
 sample=Path(__file__).parent/'data'/'sample_profile.csv'
 if sample.exists():st.download_button('Download profile template',sample.read_text(),'sample_profile.csv','text/csv')
with tabs[3]:
 st.markdown('''The linear programme first minimises battery power-plus-energy CAPEX. A second pass maximises useful solar delivery within that optimal capital budget. It enforces solar-only charging, load balance, charge/discharge power, state-of-charge bounds, cyclic daily inventory and the selected target. An infeasible result means no cyclic dispatch meets the assumptions; a larger battery cannot create energy.

A morning battery inventory comes from the previous day's solar in the repeating cycle. This does not establish that a cloudy multi-day sequence can be served. The 95% power factor is an engineering derating, not probabilistic outage modelling.

The synthetic solar curve peaks at 75% of installed capacity and yields about 5.75 equivalent full-output hours on the base day. Scaling weather is a sensitivity, not a forecast. No geographic transmission limits, generator commitment, grid reserves or seasonal reliability are modelled.

Demand shifting, solar expansion, transmission and storage should be coordinated. ToD pricing needs working interval metering and controllable loads. Water and thermal storage can avoid some electricity-storage duty. Office-hour or time-zone changes require observed behavioural responses; clock changes alone do not create solar electricity.''')
 st.markdown('[National storage planning context](https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=2290015&lang=2&reg=48) · [IEA: nighttime demand](https://www.iea.org/commentaries/india-s-electricity-demand-grows-at-night-managing-rising-cooling-demand)')
 st.caption('Research simulator. Copyright 2026 R. Gopalakrishnan. All rights reserved. Publicly visible source does not grant an open-source licence.')
