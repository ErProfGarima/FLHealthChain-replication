"""Final FL experiments (resumable: each run saved to results/fl/<name>.json)."""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flsim, numpy as np
PREFIX = sys.argv[1]; PART = int(sys.argv[2]); NPART = int(sys.argv[3])
CFG = dict(T=20, E=1, B=int(os.environ.get('FL_B', 64)), lr=float(os.environ.get('FL_LR', 0.01)), S=1.0)
flsim.HIDDEN = (32, 16)
os.makedirs('results/fl', exist_ok=True)
X, y, s20 = flsim.load(PREFIX)
jobs = []
for seed in range(5):
    jobs.append(('central', None, 20, False, seed))
    jobs.append(('local', None, 20, False, seed))
    for eps in [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 64.0, float("inf")]:
        jobs.append(('fl', eps, 20, False, seed))
    for K in [5, 10, 30]:
        for eps in [1.0, float('inf')]:
            jobs.append(('fl', eps, K, False, seed))
    for eps in [1.0, float('inf')]:
        jobs.append(('fl', eps, 20, True, seed))
sites = {20: s20}
for i, (kind, eps, K, w, seed) in enumerate(jobs):
    if i % NPART != PART: continue
    name = f'{kind}_eps{eps}_K{K}_w{int(w)}_s{seed}'
    path = f'results/fl/{name}.json'
    if os.path.exists(path): continue
    t = time.time()
    if kind == 'central':
        r = flsim.run_centralised(X, y, seed, epochs=CFG['T'], B=CFG['B'], lr=1e-3)
    elif kind == 'local':
        r = flsim.run_local_only(X, y, s20, seed, B=CFG['B'], lr=1e-3)
    else:
        if K not in sites: sites[K] = flsim.resite(PREFIX, X, K)
        r = flsim.run(X, y, sites[K], eps if eps is not None else float('inf'), seed, weighted=w, log_rounds=True, **CFG)
    r['runtime_s'] = time.time() - t; r['name'] = name
    json.dump(r, open(path, 'w'))
    print(name, round(r['auroc'], 4), round(r['runtime_s'], 1), flush=True)
