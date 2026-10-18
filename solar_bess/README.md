# Solar, Demand & BESS Policy Lab
**R. Gopalakrishnan** · 18 October 2026

A Streamlit research simulator for solar consumption targets, demand flexibility, battery design and storage-as-a-service screening. Defaults are synthetic; no confidential operating data, API credentials or personal data are bundled.

## Deploy on Streamlit Community Cloud
- Repository: `gopalakrishnan1975/CoalRailPowerSimulator`
- Branch: `main`
- Main file path: `solar_bess/app.py`
- Python: **3.11 or 3.12**
- Dependencies: `solar_bess/requirements.txt`, alongside the entrypoint.
- No secrets or backend services required.

From the repository root, run:
```bash
python -m pip install -r solar_bess/requirements.txt
python -m streamlit run solar_bess/app.py
```
Tests from the repository root:
```bash
python -m unittest discover -s solar_bess -p 'test_*.py' -v
```
The original coal simulator remains deployable from its root entrypoint. This solar application has its own dependency file.

## Targets
`Integrated daytime energy` means at least the selected share of total 06:00-18:00 energy. `Every daylight hour` means at least that share in each hourly interval. Optional evening supply covers 18:00-22:00. Daytime means the fixed IST accounting window, not location-specific sunrise.

## Inputs and outputs
- Solar GW and weather scale the synthetic 12-hour solar curve; it peaks at 75% of nameplate and yields approximately 5.75 full-output hours on the base day.
- Base demand peak scales the bundled hourly shape. Shifting moves GW from each hour 18-24 into each hour 10-16, conserving daily energy. The resulting peak can exceed the unshifted peak.
- Sector GWh and achieved-participation controls are illustrative demand-response inputs, not estimates of sector flexibility or office-hour/time-zone effects.
- BESS GW is nameplate power with derating; BESS GWh includes DoD and end-of-life retention. Usable internal GWh and AC deliverable GWh are distinct outputs.
- Economics compare identical delivered duty. Service capacity expands if a fixed-duration quote needs more MW to cover required MWh. Costs include charging electricity and exclude direct solar, network charges, subsidies, taxes, DR costs and unverified ancillary revenues.

## Model and limitations
The LP minimises battery power and energy CAPEX at fixed solar and load. A second pass maximises useful solar within the optimal budget. It enforces solar-only charging, supply balance, battery power/SOC bounds and cyclic daily inventory. See `docs/METHOD.md` for equations.
A one-day, one-node optimum is not a national forecast or an annual reliability certificate. No unit commitment, network congestion, reserve, probabilistic outage or multi-day weather model is included. The simple power factor is an engineering derating.

## Custom profiles
Upload the schema in `data/sample_profile.csv`: exactly 24 rows, `hour,load_GW,solar_GW`, hours 0-23 in order. Imports bypass synthetic supply, load, weather and demand shifting. Use consistent AC boundaries, timezone and hourly averages. Missing data must not be replaced with zeros without investigation.
Streamlit uploads are processed on the app server. This app does not deliberately persist them or call third-party data APIs. Use suitable hosting for confidential data.

## Reproducibility
`solar_model.py`: independent numerical engine; `app.py`: UI; `test_model.py`: model checks; `data/sample_profile.csv`: synthetic profile; `data/scenario_results.json`: reproducible scenario results; `docs/METHOD.md`: formulas and scope.
Run `python solar_bess/run_scenarios.py` from the repository root to reproduce bundled results. Run `python -m unittest discover -s solar_bess -v` for tests.

Copyright 2026 R. Gopalakrishnan. All rights reserved. Public source visibility does not grant an open-source licence.
