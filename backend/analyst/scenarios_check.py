"""Quick scenario checks for the optimiser (run: python scenarios_check.py). Uses whatever is in ./data."""
import copy, json
from . import optimizer
from .run_demo import HYPOTHETICAL_CLIENT as H

def run(name, **over):
    p = copy.deepcopy(H); p.update(over)
    r = optimizer.recommend(p)
    print(f"\n=== {name}: status={r['status']}")
    if r["status"] == "OK":
        for k, o in r["options"].items():
            ho = {x['asset']: x['weight_pct'] for x in o['holdings']}
            print(f"  {k}: vol {o['metrics']['vol_annualised_pct']}%  exp {o['metrics']['expected_return_pct']}%  "
                  f"cash {ho.get('CASH',0)}%  holdings {len(ho)}")
        if r['client']['excluded_assets']: print("  excluded:", r['client']['excluded_assets'])
    else:
        print(json.dumps({k: v for k, v in r.items() if k != 'status'}, indent=1, default=str)[:700])
    return r

# 1 monotonic risk appetite -> option C volatility
vols = []
for a in (1, 2, 3, 4, 5):
    r = run(f"risk appetite {a}", risk_appetite=a)
    vols.append(r["options"]["C"]["metrics"]["vol_annualised_pct"])
print("\nC vol by appetite 1..5:", vols, "monotone non-decreasing:", all(x <= y + 1e-6 for x, y in zip(vols, vols[1:])))

run("exclude Energy sector (oil + gas)", exclusions=["Energy"], asset_limits={})
run("exclude bonds but require bonds >=10% (should be INFEASIBLE)", exclusions=["bonds"])
run("tight loss limit 0.5% with appetite 5", max_loss_pct=0.5, risk_appetite=5)
run("shorting requested (should be INVALID)", allow_leverage_or_shorting=True)
run("missing fields", capital=None)
run("no illiquid allowed", max_illiquid_pct=0)
