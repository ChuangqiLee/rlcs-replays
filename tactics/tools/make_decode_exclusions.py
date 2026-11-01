import json,glob,pandas as pd,sys
R=sys.argv[1]; ex={}; per={}
for season in ["rlcs-21-22","rlcs-22-23","rlcs-2024","rlcs-2025"]:
    for f in sorted(glob.glob(f"{R}/{season}/compact-*.parquet")):
        t=pd.read_parquet(f,columns=["replay_id","state_decoding","state_decoding_details"])
        for r in t.itertuples():
            d=json.loads(r.state_decoding_details) if isinstance(r.state_decoding_details,str) else {}
            if r.state_decoding=="per_replay_decoded" and d.get("failures"):
                ex[r.replay_id]=sorted(d["failures"]); per[r.replay_id]=season
json.dump({"source":"generated from compact metadata (dev seasons only) by mkx.py","excluded":ex,"season":per},open(f"{R}/decode_exclusions.json","w"),indent=1)
print(len(ex),per)
