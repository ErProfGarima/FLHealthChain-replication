import sys, json, itertools
sys.path.insert(0, '.')
import flsim, numpy as np
X, y, s = flsim.load('final/c')
out = []
for h, lr, B in [((), 0.03, 64), ((), 0.1, 256), ((16,), 0.01, 64), ((16,), 0.03, 256), ((32, 16), 0.01, 64), ((32, 16), 0.01, 256)]:
    flsim.HIDDEN = h
    for eps in [1.0, 4.0, float('inf')]:
        a = [flsim.run(X, y, s, eps, seed=sd, E=1, B=B, lr=lr, S=1.0, val_mode=True)['auroc'] for sd in (0, 1, 2)]
        row = {'hidden': list(h), 'lr': lr, 'B': B, 'eps': eps, 'val_auroc': float(np.mean(a)), 'all': a}
        out.append(row); print(row, flush=True)
json.dump(out, open('tune_val_final.json', 'w'), indent=1)
