"""Federated DP-SGD simulation for FLHealthChain (numpy, exact per-example clipping).
Record-level (epsilon, delta)-DP per hospital via Poisson subsampling + Gaussian mechanism,
accounted with the RDP accountant of Google's dp_accounting library."""
import numpy as np, pandas as pd, json, functools
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
from sklearn.model_selection import train_test_split
from sklearn.cluster import KMeans
import absl.logging
absl.logging.set_verbosity(absl.logging.ERROR)
import dp_accounting as dpa
from dp_accounting import rdp

DELTA = 1e-5

# ---------------- data ----------------
def load(prefix):
    X = pd.read_csv(f'{prefix}_X.csv', index_col=0)
    y = pd.read_csv(f'{prefix}_y.csv', index_col=0).iloc[:, 0]
    s = pd.read_csv(f'{prefix}_site.csv', index_col=0).iloc[:, 0]
    return X, y.loc[X.index], s.loc[X.index]

def resite(prefix, X, K, seed=0):
    P = pd.read_csv(prefix.rsplit('/', 1)[0] + '/coords.csv', index_col=0).loc[X.index]
    return pd.Series(KMeans(n_clusters=K, n_init=10, random_state=seed).fit(P.values).labels_, index=X.index)

def preprocess(Xtr, Xte):
    count_cols = [c for c in Xtr.columns if c.startswith('n_')]
    Xtr = Xtr.copy(); Xte = Xte.copy()
    for c in count_cols:
        Xtr[c] = np.log1p(Xtr[c]); Xte[c] = np.log1p(Xte[c])
    med = Xtr.median()
    miss_tr = Xtr.isna().astype(float).add_suffix('_missing')
    miss_te = Xte.isna().astype(float).add_suffix('_missing')
    keep = [c for c in miss_tr.columns if 0.02 < miss_tr[c].mean() < 0.98]
    Xtr = Xtr.fillna(med); Xte = Xte.fillna(med)
    lo, hi = Xtr.quantile(0.01), Xtr.quantile(0.99)
    rng = (hi - lo).replace(0, 1)
    Xtr = ((Xtr - lo) / rng).clip(0, 1); Xte = ((Xte - lo) / rng).clip(0, 1)
    Xtr = pd.concat([Xtr, miss_tr[keep]], axis=1); Xte = pd.concat([Xte, miss_te[keep]], axis=1)
    return Xtr.values.astype(np.float64), Xte.values.astype(np.float64)

# ---------------- model: MLP d -> h_1 -> ... -> 2 (ReLU, softmax) ----------------
HIDDEN = (32, 16)

def init(d, rng, hidden=None):
    hidden = HIDDEN if hidden is None else hidden
    dims = [d, *hidden, 2]; W = []
    for a, b in zip(dims[:-1], dims[1:]):
        W += [rng.normal(0, np.sqrt(2.0 / a), (a, b)), np.zeros(b)]
    W[-2] = np.zeros_like(W[-2])          # zero-initialised output layer: initial prediction is constant
    return W

def n_params(W): return int(sum(w.size for w in W))

def forward(W, X):
    hs = [X]; h = X
    nl = len(W) // 2
    for l in range(nl - 1):
        h = np.maximum(h @ W[2 * l] + W[2 * l + 1], 0); hs.append(h)
    z = h @ W[-2] + W[-1]; z = z - z.max(1, keepdims=True)
    p = np.exp(z); p /= p.sum(1, keepdims=True)
    return hs, p

def predict(W, X): return forward(W, X)[1][:, 1]

def loss(W, X, y):
    p = forward(W, X)[1]
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1))))

def per_example_grads(W, X, y):
    """Per-example gradients, each of shape (B, *param.shape)."""
    hs, p = forward(W, X)
    B = len(y); nl = len(W) // 2
    d = p.copy(); d[np.arange(B), y] -= 1
    G = [None] * len(W)
    for l in range(nl - 1, -1, -1):
        G[2 * l] = hs[l][:, :, None] * d[:, None, :]; G[2 * l + 1] = d
        if l > 0:
            d = (d @ W[2 * l].T) * (hs[l] > 0)
    return G

class SGDM:
    def __init__(self, W, lr, mom=0.9): self.lr = lr; self.mom = mom; self.m = [np.zeros_like(w) for w in W]
    def step(self, W, G):
        for i in range(len(W)):
            self.m[i] = self.mom * self.m[i] + G[i]; W[i] -= self.lr * self.m[i]

OPT = 'adam'

class Adam:
    def __init__(self, W, lr): self.lr = lr; self.m = [np.zeros_like(w) for w in W]; self.v = [np.zeros_like(w) for w in W]; self.t = 0
    def step(self, W, G):
        self.t += 1; b1, b2 = 0.9, 0.999
        for i in range(len(W)):
            self.m[i] = b1 * self.m[i] + (1 - b1) * G[i]; self.v[i] = b2 * self.v[i] + (1 - b2) * G[i] ** 2
            mh = self.m[i] / (1 - b1 ** self.t); vh = self.v[i] / (1 - b2 ** self.t)
            W[i] -= self.lr * mh / (np.sqrt(vh) + 1e-8)

def local_train(W, X, y, steps, B, sigma, C, lr, rng, dp=True):
    W = [w.copy() for w in W]; opt = Adam(W, lr) if OPT == 'adam' else SGDM(W, lr); N = len(y); q = min(1.0, B / N); Be = q * N
    for _ in range(steps):
        if dp:
            idx = np.nonzero(rng.random(N) < q)[0]          # Poisson subsampling
            if len(idx) == 0:
                G = [rng.normal(0, sigma * C, w.shape) / Be for w in W]
            else:
                g = per_example_grads(W, X[idx], y[idx])
                norms = np.sqrt(sum((gi.reshape(len(idx), -1) ** 2).sum(1) for gi in g))
                f = np.minimum(1.0, C / (norms + 1e-12))
                G = [((gi * f.reshape((-1,) + (1,) * (gi.ndim - 1))).sum(0) + rng.normal(0, sigma * C, gi.shape[1:])) / Be for gi in g]
        else:
            idx = rng.choice(N, size=min(B, N), replace=False)
            g = per_example_grads(W, X[idx], y[idx]); G = [gi.mean(0) for gi in g]
        opt.step(W, G)
    return W

# ---------------- privacy accounting ----------------
@functools.lru_cache(maxsize=None)
def epsilon(sigma, q, steps, delta=DELTA):
    a = rdp.RdpAccountant(); a.compose(dpa.PoissonSampledDpEvent(q, dpa.GaussianDpEvent(sigma)), steps)
    return a.get_epsilon(delta)

@functools.lru_cache(maxsize=None)
def sigma_for(eps_target, q, steps, delta=DELTA):
    lo, hi = 0.3, 200.0
    if epsilon(hi, q, steps, delta) > eps_target: return hi
    for _ in range(40):
        mid = (lo + hi) / 2
        if epsilon(mid, q, steps, delta) > eps_target: lo = mid
        else: hi = mid
    return hi

# ---------------- federated run ----------------
QSCALE = 4096

def run(X, y, site, eps, seed, T=20, E=1, B=64, C=1.0, lr=1e-3, weighted=False, test_frac=0.2, log_rounds=False, S=1.0, val_mode=False):
    rng = np.random.default_rng(seed)
    idx_tr, idx_te = train_test_split(np.arange(len(y)), test_size=test_frac, stratify=y.values, random_state=seed)
    if val_mode:   # hyperparameter selection: validation = 20% of the training split
        idx_tr, idx_te = train_test_split(idx_tr, test_size=0.2, stratify=y.values[idx_tr], random_state=seed + 1000)
    Xtr_df, Xte_df = X.iloc[idx_tr], X.iloc[idx_te]
    Xtr, Xte = preprocess(Xtr_df, Xte_df)
    ytr, yte = y.values[idx_tr], y.values[idx_te]
    str_ = site.values[idx_tr]
    sites = sorted(set(str_))
    W = init(Xtr.shape[1], rng)
    dp = eps is not None and np.isfinite(eps)
    info = []
    for k in sites:
        n = int((str_ == k).sum()); steps = max(1, int(round(E * n / B))) * T
        q = min(1.0, B / n)
        s = sigma_for(float(eps), round(q, 6), steps) if dp else 0.0
        info.append({'site': int(k), 'n_train': n, 'q': q, 'steps_total': steps, 'sigma': s,
                     'eps': epsilon(s, round(q, 6), steps) if dp else float('inf')})
    hist = []; clip_hits = 0; n_upd = 0
    for t in range(T):
        upd, wts = [], []
        for j, k in enumerate(sites):
            m = str_ == k; n = int(m.sum())
            steps = max(1, int(round(E * n / B)))
            Wk = local_train(W, Xtr[m], ytr[m], steps, B, info[j]['sigma'], C, lr, rng, dp)
            u = [wk - w for wk, w in zip(Wk, W)]
            # update clipping to L2 norm S (post-processing) + 16-bit fixed-point quantisation exactly as proved in the circuit
            nrm = float(np.sqrt(sum((ui ** 2).sum() for ui in u)))
            fac = min(1.0, S / (nrm + 1e-12))
            u = [np.trunc(ui * fac * 0.999 * QSCALE / S) * S / QSCALE for ui in u]
            clip_hits += int(nrm > S); n_upd += 1
            upd.append(u); wts.append(n if weighted else 1.0)
        wts = np.array(wts, float) / np.sum(wts)
        W = [w + sum(a * u[i] for a, u in zip(wts, upd)) for i, w in enumerate(W)]
        if log_rounds:
            hist.append({'round': t + 1, 'train_loss': loss(W, Xtr, ytr), 'test_loss': loss(W, Xte, yte),
                         'test_auroc': float(roc_auc_score(yte, predict(W, Xte)))})
    p = predict(W, Xte)
    thr = np.quantile(predict(W, Xtr), 1 - ytr.mean())          # prevalence-matched threshold from training data
    yhat = (p >= thr).astype(int)
    tpr = (yhat[yte == 1] == 1).mean(); tnr = (yhat[yte == 0] == 0).mean()
    upd_norms = [float(np.sqrt(sum((ui ** 2).sum() for ui in u))) for u in upd]
    return {'eps_target': eps if dp else None, 'eps_max_site': max(i['eps'] for i in info) if dp else None,
            'seed': seed, 'n_sites': len(sites), 'auroc': float(roc_auc_score(yte, p)),
            'auprc': float(average_precision_score(yte, p)), 'brier': float(brier_score_loss(yte, p)),
            'accuracy_0.5': float(((p >= 0.5) == yte).mean()), 'balanced_acc': float((tpr + tnr) / 2),
            'sensitivity': float(tpr), 'specificity': float(tnr), 'prevalence_test': float(yte.mean()),
            'n_params': n_params(W), 'n_features_model': Xtr.shape[1], 'site_info': info, 'history': hist,
            'last_round_update_norms': upd_norms, 'weighted': weighted, 'update_clip_S': S, 'update_clip_rate': clip_hits / max(1, n_upd), 'T': T, 'E': E, 'B': B, 'C': C, 'lr': lr}

def run_centralised(X, y, seed, epochs=20, B=64, lr=1e-3, test_frac=0.2):
    rng = np.random.default_rng(seed)
    idx_tr, idx_te = train_test_split(np.arange(len(y)), test_size=test_frac, stratify=y.values, random_state=seed)
    Xtr, Xte = preprocess(X.iloc[idx_tr], X.iloc[idx_te]); ytr, yte = y.values[idx_tr], y.values[idx_te]
    W = init(Xtr.shape[1], rng)
    W = local_train(W, Xtr, ytr, epochs * len(ytr) // B, B, 0, 1, lr, rng, dp=False)
    p = predict(W, Xte)
    return {'seed': seed, 'auroc': float(roc_auc_score(yte, p)), 'auprc': float(average_precision_score(yte, p)),
            'brier': float(brier_score_loss(yte, p)), 'accuracy_0.5': float(((p >= 0.5) == yte).mean())}

def run_local_only(X, y, site, seed, epochs=20, B=64, lr=1e-3, test_frac=0.2):
    """Each hospital trains alone (non-private) on its own data; AUROC of each model on the global test set."""
    rng = np.random.default_rng(seed)
    idx_tr, idx_te = train_test_split(np.arange(len(y)), test_size=test_frac, stratify=y.values, random_state=seed)
    Xtr, Xte = preprocess(X.iloc[idx_tr], X.iloc[idx_te]); ytr, yte = y.values[idx_tr], y.values[idx_te]
    st = site.values[idx_tr]; aucs = []
    for k in sorted(set(st)):
        m = st == k
        if ytr[m].sum() < 2: continue
        W = init(Xtr.shape[1], rng)
        W = local_train(W, Xtr[m], ytr[m], max(1, epochs * int(m.sum()) // B), B, 0, 1, lr, rng, dp=False)
        aucs.append(float(roc_auc_score(yte, predict(W, Xte))))
    return {'seed': seed, 'auroc': float(np.mean(aucs)), 'auroc_sd_sites': float(np.std(aucs)), 'n_sites': len(aucs)}
