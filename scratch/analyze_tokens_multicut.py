import json, glob, sys
from collections import defaultdict
SUF = sys.argv[1] if len(sys.argv)>1 else 'k5'
LIM = int(sys.argv[2]) if len(sys.argv)>2 else None

def calls(run, sid, kind):
    g=sorted(glob.glob(f"data/simulations/{run}/artifacts/**/sim_{sid}/llm_debug/*{kind}*.json",recursive=True))
    return [json.load(open(f)) for f in g]

def usage(d):
    u=d.get('response',{}).get('usage') or {}
    pt=u.get('prompt_tokens') or 0; ct=u.get('completion_tokens') or 0
    return pt, ct, d.get('response',{}).get('cost') or 0.0

print(f"{'format':>12} | {'cuts':>4} {'summ_in':>7} {'blk_out':>7} {'summ_$':>7} | {'ag_calls':>8} {'ag_in':>7} {'ag_out':>6} | {'TOTAL_tok':>9} {'TOTAL_$':>8}")
for arm in ('prose','md','json','json_struct'):
    run=f"taskC_{arm}_{SUF}"
    try: S=json.load(open(f"data/simulations/{run}/results.json"))['simulations']
    except Exception: print(f"{arm}: (no results)"); continue
    agg=defaultdict(list)
    if LIM: S=S[:LIM]
    for s in S:
        cons=calls(run,s['id'],'consolidation_summary')
        ag=calls(run,s['id'],'agent_response')
        s_in=sum(usage(d)[0] for d in cons); s_out=sum(usage(d)[1] for d in cons); s_cost=sum(usage(d)[2] for d in cons)
        a_in=sum(usage(d)[0] for d in ag); a_out=sum(usage(d)[1] for d in ag); a_cost=sum(usage(d)[2] for d in ag)
        agg['cuts'].append(len(cons)); agg['s_in'].append(s_in); agg['s_out'].append(s_out); agg['s_cost'].append(s_cost)
        agg['a_calls'].append(len(ag)); agg['a_in'].append(a_in); agg['a_out'].append(a_out)
        agg['tot'].append(s_in+s_out+a_in+a_out); agg['cost'].append(s_cost+a_cost)
    m=lambda k: sum(agg[k])/len(agg[k])
    print(f"{arm:>12} | {m('cuts'):>4.0f} {m('s_in'):>7.0f} {m('s_out'):>7.0f} {m('s_cost')*1000:>7.2f} | {m('a_calls'):>8.0f} {m('a_in'):>7.0f} {m('a_out'):>6.0f} | {m('tot'):>9.0f} {m('cost')*1000:>8.2f}")
print("\n(summ_in=summarizer input=gather transcripts; blk_out=summarizer output=block gen;")
print(" ag_in=agent input incl blocks re-sent every turn; $ in units of 1e-3. All per-trial avg.)")
