# Coal–Rail–Power Simulator

Author: **R. Gopalakrishnan**

Public code edition of the multi-location coal inventory and electricity policy laboratory. All bundled mine, plant, route and corridor inputs are synthetic.

## Run

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

For Streamlit Community Cloud select this repository, branch `main`, entry point `app.py`, and Python 3.11 or 3.12. The app requires no API keys or backend service.

The code models pithead, plant and in-transit coal, finite rakes, hourly residual demand after solar/wind, carrying costs, candidate price mechanisms and finite-policy best responses. Results are research demonstrations. Price search is a finite candidate comparison; equilibrium checks apply only to the tested strategies and scenario sample.

## Checks

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Optional HTTP adapters use `requirements-services.txt`; `docker compose up --build` starts four localhost-bound research services. The Streamlit app runs without them.

Copyright 2026 R. Gopalakrishnan. All rights reserved; no open-source license is granted by making this source visible.
