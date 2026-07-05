import json, glob, re, sys

def sims(run):
    return json.load(open(f"data/simulations/{run}/results.json"))['simulations']

def blocks_for_sim(run, sid):
    g=sorted(glob.glob(f"data/simulations/{run}/artifacts/**/sim_{sid}/llm_debug/*consolidation_summary*.json",recursive=True))
    return [json.load(open(f))['response']['content'] for f in g]

def needle(b):
    return {
      'visa7447': ('7447' in b) or ('visa' in b.lower()),
      'mc_leak': ('1052991' in b) or ('1780' in b) or ('mastercard' in b.lower()),
      'after11': ('11:00' in b) or ('after 11' in b.lower()),
      'cheapest': 'cheapest' in b.lower(),
    }

def final_card(sim):
    cards=[]
    for m in sim['messages']:
        for tc in (m.get('tool_calls') or []):
            if tc.get('name')=='update_reservation_flights':
                cards.append((tc.get('arguments') or {}).get('payment_id'))
    return cards[-1] if cards else None

def wrote_flight(sim):
    fl=[]
    for m in sim['messages']:
        for tc in (m.get('tool_calls') or []):
            if tc.get('name')=='update_reservation_flights':
                fl=[f.get('flight_number') for f in (tc.get('arguments') or {}).get('flights',[])]
    return fl

MAXB = 2  # expected cuts per trial (== distractor searches)
SUF = sys.argv[1] if len(sys.argv)>1 else "k5"
LIM = int(sys.argv[2]) if len(sys.argv)>2 else None
for run in [f"taskC_{a}_{SUF}" for a in ('prose','md','json','json_struct')]:
    try: S=sims(run)
    except Exception: print(f"{run}: (no results)"); continue
    if LIM: S=S[:LIM]
    print(f"\n===== {run} =====")
    b_visa=[0]*MAXB; b_mc=[0]*MAXB; visa_all=0; db=0; dbn=0; com=0; comn=0; rightcard=0; wrongcard=0; nfull=0
    for s in S:
        bl=blocks_for_sim(run, s['id'])
        ns=[needle(b) for b in bl]
        for i,n in enumerate(ns[:MAXB]):
            if n['visa7447']: b_visa[i]+=1
            if n['mc_leak']: b_mc[i]+=1
        if len(ns)>=MAXB:
            nfull+=1
            if all(n['visa7447'] for n in ns[:MAXB]): visa_all+=1
        card=final_card(s)
        if card=='credit_card_3092185': rightcard+=1
        elif card=='credit_card_1052991': wrongcard+=1
        ri=s.get('reward_info') or {}
        d=(ri.get('db_check') or {}).get('db_reward')
        c=(ri.get('reward_breakdown') or {}).get('COMMUNICATE')  # separate, NOT multiplied into DB
        if d is not None: db+=d; dbn+=1
        if c is not None: com+=c; comn+=1
        print(f"  trial: cuts={len(bl)} visa@blk={[int(n['visa7447']) for n in ns]} mc_leak={[int(n['mc_leak']) for n in ns]} final_card={card} flt={wrote_flight(s)} DB={d} COM={c}")
    print(f"  -- visa survival per block: {b_visa} | mc-leak per block: {b_mc}")
    print(f"  -- visa survived ALL {MAXB} cuts: {visa_all}/{nfull} | right card: {rightcard} | wrong(MC): {wrongcard}")
    print(f"  -- DB: {db}/{dbn}  |  COMMUNICATE: {com}/{comn}  (reported separately, not as a product)")
