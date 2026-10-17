"""Streamlit entry point. Author: R. Gopalakrishnan."""
from dataclasses import asdict, replace
import io,json,zipfile,copy,hashlib
from pathlib import Path
import streamlit as st
import pandas as pd
from coalpower.model import Config,load_network,validate_network,FIELDS
from coalpower.engine import simulate,compare_policies,mechanism_search
from coalpower.game import best_response_lab,counterexample

st.set_page_config(page_title='Coal–Rail–Power Policy Laboratory',layout='wide')
st.title('Coal–Rail–Power Policy Laboratory')
st.caption('R. Gopalakrishnan · Multi-location inventory, renewable competition and agent incentives')
st.info('Research prototype. Default data and price rules are synthetic. Candidate search is not a proof of optimal pricing. Electricity is a pooled grid; coal movements use complete rakes.')

with st.sidebar:
    st.header('Scenario')
    days=st.slider('Simulation days',15,180,60)
    seed=st.number_input('Random seed',0,100000,42)
    demand=st.slider('Mean gross demand (MW)',500,4000,1800,100)
    solar=st.slider('Solar nameplate (MW)',0,4000,1100,100)
    wind=st.slider('Wind nameplate (MW)',0,2500,450,50)
    dvol=st.slider('Demand uncertainty',0.,.5,.12,.01)
    rvol=st.slider('Renewable uncertainty',0.,.8,.25,.01)
    shock=st.slider('Daily common disruption probability',0.,.4,.08,.01)
    severity=st.slider('Disruption severity',0.,1.,.5,.05)
    st.header('Inventory and prices')
    policy=st.selectbox('Plant decision policy',['dynamic','static','coordinated'])
    rate=st.slider('Annual inventory capital rate (%)',0.,40.,12.,1.)/100
    cover=st.slider('Maximum plant cover / static target (days)',1.,25.,10.,1.)
    minecover=st.slider('Pithead working cover (days)',0.,20.,5.,1.)
    share=st.slider('Safety protection shifted upstream',0.,1.,.35,.05)
    markup=st.slider('Coal offer markup (INR/tonne)',0,1200,200,50)
    rail=st.slider('Rail capacity premium (INR/tonne)',0,600,60,20)
    gain=st.slider('Congestion price response (INR/tonne)',0,500,100,25)
    smoothing=st.slider('Daily coal-price adjustment fraction',0.,1.,.25,.05)
    payment=st.slider('Verified plant stock payment (INR/tonne/day)',0.,10.,2.,.5)
    penalty=st.number_input('Plant availability shortfall penalty (INR/MWh)',0,100000,2000,500)
    voll=st.number_input('Social loss of unserved electricity (INR/MWh)',1000,1000000,100000,5000)
    st.header('Rail fleet')
    fleet=st.slider('Available compatible rakes',5,120,45)
    ret=st.slider('Empty return + turnaround days',0,8,2)

cfg=Config(days=days,seed=int(seed),demand_mw=demand,solar_mw=solar,wind_mw=wind,demand_volatility=dvol,renewable_volatility=rvol,shock_probability=shock,shock_severity=severity,annual_carry_rate=rate,plant_cover_days=cover,mine_cover_days=minecover,pithead_share=share,coal_markup=markup,rail_premium=rail,congestion_gain=gain,price_smoothing=smoothing,availability_payment=payment,performance_penalty_mwh=penalty,value_lost_load_mwh=voll,fleet_rakes=fleet,empty_return_days=ret,policy=policy)
tabs=st.tabs(['Network & data','Run & compare','Price and placement search','Agent convergence','Technical notes'])
with tabs[0]:
    st.subheader('Edit locations and routes')
    st.write('IDs link the four master tables. Add mines/plants and their routes together. Stocks and capacities are tonnes; costs are INR. Inputs use the units shown in the table column names; all bundled examples are synthetic.')
    default=load_network();network={}
    for name in FIELDS:
        with st.expander(name.title(),expanded=name in ['plants','routes']):
            upload=st.file_uploader(f'Import {name}.csv',type='csv',key='upload_'+name)
            table=pd.read_csv(upload) if upload else pd.DataFrame(default[name])
            edited=st.data_editor(table,num_rows='dynamic',key='edit_'+name,width='stretch')
            network[name]=edited.to_dict('records')
    try:
        validate_network(network);cfg.validate();valid=True
        st.success('Network references, numeric domains and capacities validated.')
    except (ValueError,TypeError) as e:
        valid=False;st.error(str(e))
    st.download_button('Download current network JSON',json.dumps(network,indent=2),file_name='network.json')

@st.cache_data(show_spinner=False)
def cached_run(net,c):
    return simulate(net,Config(**c))

with tabs[1]:
    st.subheader('Coal, electricity and cost outcomes')
    if st.button('Run scenario',type='primary',disabled=not valid):
        with st.spinner('Simulating stock, rake and dispatch decisions…'):
            st.session_state['result']=cached_run(network,asdict(cfg))
            st.session_state['run_network']=copy.deepcopy(network)
    if 'result' in st.session_state:
        r=st.session_state['result'];s=r['summary'];d=r['daily']
        if s['config']!=asdict(cfg) or s['network_sha256']!=hashlib.sha256(json.dumps(network,sort_keys=True).encode()).hexdigest():st.warning('Controls have changed. Run again to refresh results.')
        a,b,c,e=st.columns(4)
        a.metric('Social cost (INR million)',f"{s['social_cost_inr']/1e6:,.2f}")
        b.metric('Unserved energy (MWh)',f"{s['unserved_mwh']:,.0f}")
        c.metric('Plant + transit carrying (INR million)',f"{s['private_plant_and_pipeline_carry_inr']/1e6:,.2f}")
        e.metric('Reserve funding (INR million)',f"{s['availability_payments_inr']/1e6:,.2f}")
        st.caption('Social cost includes real costs, outage loss and an explicit terminal inventory adjustment. It excludes domestic coal/freight payments and penalties. Private profits are separate.')
        st.write('Inventory by physical location (tonnes)')
        st.area_chart(d.set_index('day')[['pithead_t','plant_t','in_transit_t']])
        st.write('Thermal generation and shortages after renewable competition (MWh/day)')
        st.line_chart(d.set_index('day')[['thermal_requirement_mwh','generation_mwh','unserved_mwh']])
        st.write('Individual plant inventories (tonnes)')
        st.line_chart(r['stocks'].query("location == 'plant'").pivot(index='day',columns='node',values='stock_t'))
        st.write('Mine coal offers (INR/tonne)')
        st.line_chart(r['prices'].pivot(index='day',columns='agent',values='coal_offer_t'))
        st.write('Rail capacity and congestion signal (INR/tonne)')
        st.line_chart(r['prices'].groupby('day')['rail_signal_t'].first())
        st.write('Rake use and loading')
        st.line_chart(d.set_index('day')[['rakes_busy','rakes_loaded']])
        st.dataframe(pd.DataFrame(s['agent_utilities_inr'].items(),columns=['agent','private_horizon_utility_inr']),hide_index=True)
        st.caption(f"Largest mass reconciliation error: {s['mass_error_max_t']:.8f} tonnes. Results use the controls saved in the download, not necessarily today's sidebar state.")
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('summary.json',json.dumps(s,indent=2))
            z.writestr('network.json',json.dumps(st.session_state['run_network'],indent=2))
            for name in ['daily','stocks','prices','events']:z.writestr(name+'.csv',r[name].to_csv(index=False))
        st.download_button('Download run results ZIP',buf.getvalue(),file_name='coal_power_run.zip')
    if st.button('Compare three policies on the same three seeds',disabled=not valid):
        with st.spinner('Running matched scenarios…'):frame=compare_policies(network,cfg)
        st.dataframe(frame,width='stretch')
        st.bar_chart(frame.groupby('policy')[['social_cost_inr','unserved_mwh']].mean()['social_cost_inr'])
        st.download_button('Download comparison',frame.to_csv(index=False),file_name='policy_comparison.csv')

with tabs[2]:
    st.subheader('Search carrying-cost-aware location and price candidates')
    st.write('Search 18 candidate combinations of upstream safety share, rail premium and plant reserve payment. Agents still follow their own stock rule. Two training seeds are separate from a held-out seed. All parameters outside this grid remain fixed.')
    budget=st.number_input('Mean reserve funding budget (INR million)',0.,1000.,10.,1.)*1e6
    if st.button('Search candidate mechanisms',disabled=not valid):
        with st.spinner('Evaluating candidate mechanisms on common scenarios…'):
            frame=mechanism_search(network,cfg,max_budget_inr=budget)
        st.dataframe(frame,width='stretch')
        feasible=frame[frame.within_budget]
        if len(feasible):
            win=feasible.iloc[0]
            st.success('Best tested candidate under the stated mean training budget; no global optimality or participation guarantee.')
            held=simulate(network,replace(cfg,policy='coordinated',seed=100003,pithead_share=float(win.pithead_share),rail_premium=float(win.rail_premium),availability_payment=float(win.availability_payment)))['summary']
            st.write({'held_out_seed':100003,'social_cost_inr':held['social_cost_inr'],'unserved_mwh':held['unserved_mwh'],'payments_inr':held['availability_payments_inr']})
            if held['availability_payments_inr']>budget:st.warning('Held-out funding exceeds the mean training budget. This is not a hard scenario-by-scenario spending guarantee.')
        else:st.warning('No candidate satisfies the mean training funding limit.')
        st.download_button('Download mechanism search',frame.to_csv(index=False),file_name='mechanism_search.csv')

with tabs[3]:
    st.subheader('Will policies converge? Test it.')
    st.write('Each mine chooses a coal markup, Railways chooses a premium, and each generator chooses a stock-cover ceiling. A best response evaluates its own horizon utility while holding other policies fixed. This is a restricted finite-policy game, not a solution of the full dynamic stochastic game.')
    mode=st.selectbox('Update order',['sequential','simultaneous','random'])
    rounds=st.slider('Maximum response rounds',2,12,5)
    probability=st.slider('Probability of accepting an improved policy',.2,1.,1.,.1)
    labdays=st.slider('Payoff simulation days',15,60,30)
    if st.button('Run agent best responses',disabled=not valid):
        with st.spinner('Evaluating strategic policy deviations…'):
            lab=best_response_lab(network,replace(cfg,days=labdays),rounds,mode,probability)
        st.write(lab['status']);st.caption(lab['qualification'])
        st.line_chart(lab['history'].set_index('round')['max_regret_inr'])
        st.dataframe(lab['history'],width='stretch')
        st.write('Evaluated policy profiles:',lab['evaluated_profiles'],'Scenario seeds:',lab['scenario_seeds'])
        st.download_button('Download convergence trace',lab['history'].to_csv(index=False),file_name='convergence.csv')
    with st.expander('Why simultaneous best responses can cycle'):
        st.write('Two agents each prefer to match the other location policy. Starting with different choices, both simultaneously copy the other and swap forever. Sequential updating reaches agreement. This toy game proves only that a blanket convergence claim is false.')
        st.dataframe(counterexample(),hide_index=True)

with tabs[4]:
    st.subheader('How to interpret the model')
    st.markdown('''- **Pithead reserve:** mine production responds to expected thermal coal use and an upstream reserve target.
- **Plant reserve:** cost-sensitive target covers replenishment time and uncertainty. Higher carrying cost can reduce its quantile; the selected cover is a ceiling in dynamic modes.
- **Renewable demand risk:** hourly solar and wind reduce residual electricity demand; plants also compete in fuel-cost merit order.
- **Coal India signal:** synthetic mine offer responds to mine stock scarcity and a chosen markup.
- **Railway signal:** synthetic capacity premium responds to requests relative to corridor capacity.
- **Convergence:** zero regret means no profitable deviation among the tested actions and seeds. It does not imply a social optimum.
- **Scope:** one compatible coal grade, pooled electricity grid, no unit commitment, explicit finite rakes and daily route/corridor limits. More complete physics and empirical calibration are required for operational use.''')
    st.caption('Public code edition. Example inputs are synthetic; technical papers are maintained separately.')
