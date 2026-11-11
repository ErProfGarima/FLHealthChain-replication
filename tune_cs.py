import sys, json
sys.path.insert(0, '.')
import flsim, numpy as np
X, y, s = flsim.load('final/c'); flsim.HIDDEN = (32, 16)
part = int(sys.argv[1]); out = []
grid = [(C, S, eps) for eps in [1.0, 8.0] for C in [0.1, 1.0] for S in [1.0, 4.0]]
for i, (C, S, eps) in enumerate(grid):
    if i % 2 != part: continue
    a = [flsim.run(X, y, s, eps, seed=sd, E=1, B=64, lr=0.01, S=S, C=C, val_mode=True)['auroc'] for sd in (0, 1)]
    row = {'C': C, 'S': S, 'eps': eps, 'val_auroc': float(np.mean(a)), 'all': a}; out.append(row); print(row, flush=True)
json.dump(out, open(f'tune_cs_{part}.json', 'w'))
