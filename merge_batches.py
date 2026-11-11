"""Concatenate Synthea CSV exports from several runs. Batches that were interrupted have their
last 5 patients removed (their records may be incomplete)."""
import sys, os, pandas as pd
out = sys.argv[1]; batches = sys.argv[2:]
files = ['patients', 'encounters', 'observations', 'conditions', 'medications', 'procedures', 'careplans']
os.makedirs(out, exist_ok=True)
drop = set()
for b in batches:
    trunc = b.endswith(':trunc'); path = b.replace(':trunc', '')
    if trunc:
        p = pd.read_csv(f'{path}/patients.csv', usecols=['Id'], on_bad_lines='skip')
        drop |= set(p.Id.tail(5))
for f in files:
    first = True
    with open(f'{out}/{f}.csv', 'w') as fo:
        for b in batches:
            path = b.replace(':trunc', '')
            for ch in pd.read_csv(f'{path}/{f}.csv', chunksize=1_000_000, on_bad_lines='skip', dtype=str):
                col = 'Id' if f == 'patients' else 'PATIENT'
                ch = ch[~ch[col].isin(drop)].dropna(subset=[col])
                ch.to_csv(fo, header=first, index=False); first = False
    print(f, 'done', flush=True)
print('dropped patients from truncated batches:', len(drop))
