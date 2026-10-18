# Model method


The simulator solves a two-stage linear programme at fixed solar capacity and fixed demand-response inputs. Variables are direct solar A[h], solar charging C[h], battery discharge D[h], internal SOC X[h], nameplate power P and nameplate energy E. The first objective minimises c_P P + c_E E. Because the finance factor applies uniformly, this also minimises the fixed annual ownership component under the entered cost assumptions. It does not optimise solar or demand-response investment.

For every hourly interval, impose A[h] + C[h] <= S[h], and A[h] + D[h] <= L[h]. Other supply is the non-negative residual L[h] - A[h] - D[h]. This explicitly allows solar to charge storage while other generation supplies some concurrent demand when that allocation is needed for the chosen hourly target. Charging energy is solar-origin only; the model never labels thermal charging as solar consumption.

For the hourly target, A[h] + D[h] >= alpha L[h] in each daylight hour. For the integrated target, sum_day(A[h] + D[h]) >= alpha sum_day L[h]. An optional evening floor applies to each hour 18-22. Demand outside the selected targets is still served by the residual supply resource, whose adequacy is not tested here.

State evolves as X[h+1] = X[h] + eta_c C[h] - D[h]/eta_d. Enforce 0 <= X[h] <= E x DoD x SOH_EOL and X[24] = X[0]. Enforce C[h] <= P x derating and D[h] <= P x derating. All powers are GW and intervals are one hour, so interval energies are GWh. Efficiencies are both sqrt(RTE). Initial SOC is an endogenous cyclic inventory replenished by solar; no free net energy is created across the day.

A second solve maximises sum_h(A[h] + D[h]) within the minimum first-stage capital budget plus a numerical tolerance. A tiny positive charging penalty resolves unnecessary charge-throughput ties. Positive capital costs and storage losses make simultaneous charge and discharge dominated in the tested scenarios; no binary complementarity constraint is imposed. Tests check that simultaneous operations are absent in the scenario suite. Negative electricity prices, ancillary dispatch and unusual zero-cost inputs would require further treatment.

Nameplate energy includes both usable-depth and end-of-life retention allowances. AC deliverable energy is E x DoD x SOH_EOL x eta_d. The power derating is an engineering margin, not an outage probability. Economic service capacity must satisfy both required AC power and required delivered energy divided by the quoted contractual duration.

If the LP is infeasible, report that no cyclic solar-only dispatch meets the assumptions. A simple necessary energy bound is total solar generation at least the targeted daylight energy plus targeted evening energy, before losses. Passing that bound is not sufficient because chronology and losses also constrain feasibility. A production extension needs chronological multi-year scenarios, network security and complete alternative-supply costs. This one-day optimum is not a national least-cost resource-adequacy plan.


## Monetary units

1 GWh at INR 1/kWh = INR 0.1 crore. One GW contracted at INR 1 lakh/MW/month costs INR 120 crore/year. Nameplate energy cost and power cost are additive; do not double-count a bundled EPC quotation.

## Contract economics

Service GW = max(required AC power, guaranteed delivered energy / quoted hours). Capacity rent, charging energy and throughput fee are separate. The ownership-equivalent rent is the maximum service rent that equals ownership at the same performance. It is not evidence that a provider quoting less can cover the same costs.
