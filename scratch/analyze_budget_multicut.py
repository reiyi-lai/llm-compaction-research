import json, glob, sys
from collections import defaultdict

# budget -> run-dir suffix; 900 reuses the existing k-run (k20 preferred, else k5)
def run_for(arm, b):
    if b == 900:
        for suf in ('k20','k5'):
            if glob.glob(f"data/simulations/taskC_{arm}_{suf}/results.json"): return f"taskC_{arm}_{suf}"
        return f"taskC_{arm}_k20"
    return f"taskC_{arm}_b{b}"

def usage(d):
    u=d.get('response',{}).get('usage') or {}
    return (u.get('prompt_tokens') or 0), (u.get('completion_tokens') or 0)

def needle_visa(b): return ('7447' in b) or ('visa' in b.lower())

def cell(arm, b):
    run=run_for(arm,b)
    try: S=json.load(open(f"data/simulations/{run}/results.json"))['simulations']
    except Exception: return None
    ratios=[]; blk=[]; inp=[]; visa_all=0; nfull=0; db=0; dbn=0; com=0; comn=0; rc=0
    for s in S:
        g=sorted(glob.glob(f"data/simulations/{run}/artifacts/**/sim_{s['id']}/llm_debug/*consolidation_summary*.json",recursive=True))
        cuts=[json.load(open(f)) for f in g]
        for d in cuts:
            pt,ct=usage(d)
            if pt>0: ratios.append(ct/pt); blk.append(ct); inp.append(pt)
        # needle survival across all cuts
        blocks=[d.get('response',{}).get('content','') for d in cuts]
        if len(blocks)>=2:
            nfull+=1
            if all(needle_visa(b) for b in blocks[:2]): visa_all+=1
        ri=s.get('reward_info') or {}
        d_=(ri.get('db_check') or {}).get('db_reward'); c_=(ri.get('reward_breakdown') or {}).get('COMMUNICATE')
        if d_ is not None: db+=d_; dbn+=1
        if c_ is not None: com+=c_; comn+=1
        # right visa card
        for m in s['messages']:
            for tc in (m.get('tool_calls') or []):
                if tc.get('name')=='update_reservation_flights' and (tc.get('arguments') or {}).get('payment_id')=='credit_card_3092185': rc+=1; break
    avg=lambda x: sum(x)/len(x) if x else 0
    return dict(ratio=avg(ratios), blk=avg(blk), inp=avg(inp), visa=f"{visa_all}/{nfull}", db=f"{db:.0f}/{dbn}", com=f"{com:.0f}/{comn}", n=len(S))

BUDGETS=[250,500,900,1500]
print(f"{'format':>12} {'budget':>6} | {'ratio':>6} {'block':>6} {'input':>6} | {'visa_surv':>9} {'DB':>6} {'COM':>6}")
for arm in ('prose','md','json','json_struct'):
    for b in BUDGETS:
        c=cell(arm,b)
        if c is None: print(f"{arm:>12} {b:>6} | (pending)"); continue
        print(f"{arm:>12} {b:>6} | {c['ratio']:>6.3f} {c['blk']:>6.0f} {c['inp']:>6.0f} | {c['visa']:>9} {c['db']:>6} {c['com']:>6}")
    print()
print("ratio = block_tokens / summarizer_input_tokens (lower = more compression), avg over cuts")
