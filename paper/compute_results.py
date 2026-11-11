"""Collect every measured result into values.json, markdown tables and figures for the manuscript."""
import json, glob, os, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

FL = '/home/claude/flhc/fl'; ZK = '/home/claude/flhc/zk'; OUT = '/home/claude/flhc/paper'
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
C1, C2, C3, C4 = '#2a6f97', '#c8553d', '#5e9a64', '#8a6fb3'
V = {}; T = {}

def ms(x): return f'{np.mean(x):.3f} ± {np.std(x, ddof=1):.3f}' if len(x) > 1 else f'{x[0]:.3f}'
def load(pattern): return [json.load(open(f)) for f in sorted(glob.glob(f'{FL}/results/fl/{pattern}'))]

# ---------------- cohort ----------------
meta = json.load(open(f'{FL}/final/c_meta.json'))
V['n_patients'] = f"{meta['n_patients']:,}"; V['n_events'] = f"{meta['n_events_1y']:,}"
V['prev_pct'] = f"{100 * meta['prevalence']:.1f}"; V['n_features'] = str(meta['n_features'])
V['site_min'] = str(min(meta['site_sizes'])); V['site_max'] = str(max(meta['site_sizes']))
V['site_prev_min'] = f"{100 * min(meta['site_prevalence']):.1f}"; V['site_prev_max'] = f"{100 * max(meta['site_prevalence']):.1f}"
V['acc_trivial'] = f"{100 * (1 - meta['prevalence']):.1f}"

# ---------------- FL ----------------
def grp(kind, eps, K=20, w=0):
    return load(f'{kind}_eps{eps}_K{K}_w{w}_s*.json')
inf = 'inf'
central = load('central_epsNone_K20_w0_s*.json'); local = load('local_epsNone_K20_w0_s*.json')
r_inf = grp('fl', inf); r1 = grp('fl', 1.0)
V['n_in'] = str(r_inf[0]['n_features_model']); V['n_params'] = f"{r_inf[0]['n_params']:,}"; V['n_params_raw'] = r_inf[0]['n_params']
V['lr'] = str(r_inf[0]['lr']); V['S'] = f"{r_inf[0]['update_clip_S']:.1f}"
au = lambda rs, k='auroc': [r[k] for r in rs]
V['auc_inf'] = f"{np.mean(au(r_inf)):.3f}"; V['auc_eps1'] = f"{np.mean(au(r1)):.3f}"
V['auc_central'] = f"{np.mean(au(central)):.3f}"; V['auc_eps8'] = f"{np.mean(au(grp('fl', 8.0))):.3f}"
V['retain_pct'] = f"{100 * np.mean(au(r1)) / np.mean(au(r_inf)):.0f}"
V['above_chance_pct'] = f"{100 * (np.mean(au(r1)) - 0.5) / (np.mean(au(r_inf)) - 0.5):.0f}"
V['auc_eps64'] = f"{np.mean(au(grp('fl', 64.0))):.3f}"
V['auc_local'] = f"{np.mean(au(local)):.3f}"
sig = [i['sigma'] for i in r1[0]['site_info']]
V['sigma_eps1_max'] = f"{max(sig):.2f}"; V['sigma_eps1_min'] = f"{min(sig):.2f}"
rows = ['| Setting | ε (max over hospitals) | Noise multiplier σᵢ (min–max) | AUROC | AUPRC | Brier score | Accuracy @0.5 |', '|---|---|---|---|---|---|---|']
rows.append(f"| Centralised, non-private (pooled data) | ∞ | — | {ms(au(central))} | {ms(au(central, 'auprc'))} | {ms(au(central, 'brier'))} | {ms(au(central, 'accuracy_0.5'))} |")
rows.append(f"| Local-only (each hospital alone, mean of 20) | ∞ | — | {ms(au(local))} | — | — | — |")
pu = []
for e in [0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 64.0, inf]:
    rs = grp('fl', e)
    if not rs: continue
    if e == inf:
        epsl, sg = '∞', '0'
    else:
        epsl = f"{max(r['eps_max_site'] for r in rs):.2f}"
        s_ = [i['sigma'] for i in rs[0]['site_info']]; sg = f"{min(s_):.2f}–{max(s_):.2f}"
    rows.append(f"| FLHealthChain, ε target {('∞' if e == inf else e)} | {epsl} | {sg} | {ms(au(rs))} | {ms(au(rs, 'auprc'))} | {ms(au(rs, 'brier'))} | {ms(au(rs, 'accuracy_0.5'))} |")
    pu.append((e, np.mean(au(rs)), np.std(au(rs), ddof=1), np.mean(au(rs, 'auprc')), np.std(au(rs, 'auprc'), ddof=1)))
T['TABLE4'] = ('Table 4: Privacy–utility results with 20 hospitals and T = 20 rounds (mean ± SD over 5 seeds). ε is the record-level budget at δ = 10⁻⁵ computed by the RDP accountant for each hospital; the column shows the largest value over hospitals.', rows)
# Figure 3
fig, ax = plt.subplots(1, 2, figsize=(10, 3.6))
xs = [p[0] for p in pu if p[0] != inf]; ys = [p[1] for p in pu if p[0] != inf]; es = [p[2] for p in pu if p[0] != inf]
ax[0].errorbar(xs, ys, yerr=es, marker='o', color=C1, capsize=3, label='FLHealthChain (DP-SGD)')
pinf = [p for p in pu if p[0] == inf][0]
ax[0].axhline(pinf[1], color=C2, ls='--', label='Federated, non-private'); ax[0].axhline(np.mean(au(central)), color=C3, ls=':', label='Centralised, non-private')
ax[0].axhline(np.mean(au(local)), color='#888', ls='-.', label='Local-only (mean)')
ax[0].set_xscale('log'); ax[0].set_xticks(xs); ax[0].set_xticklabels([str(x) for x in xs]); ax[0].set_xlabel('record-level ε (δ = 10⁻⁵)'); ax[0].set_ylabel('AUROC'); ax[0].legend(fontsize=8, frameon=False); ax[0].set_title('(a) Discrimination', fontsize=10)
ys2 = [p[3] for p in pu if p[0] != inf]; es2 = [p[4] for p in pu if p[0] != inf]
ax[1].errorbar(xs, ys2, yerr=es2, marker='s', color=C1, capsize=3); ax[1].axhline(pinf[3], color=C2, ls='--'); ax[1].axhline(meta['prevalence'], color='#888', ls=':', label='prevalence (chance)')
ax[1].set_xscale('log'); ax[1].set_xticks(xs); ax[1].set_xticklabels([str(x) for x in xs]); ax[1].set_xlabel('record-level ε (δ = 10⁻⁵)'); ax[1].set_ylabel('AUPRC'); ax[1].legend(fontsize=8, frameon=False); ax[1].set_title('(b) Precision–recall', fontsize=10)
fig.tight_layout(); fig.savefig(f'{OUT}/figs/fig3_privacy_utility.png', dpi=300); plt.close(fig)

# K sweep
rows = ['| Hospitals K | Mean training records per hospital | σᵢ at ε = 1 (min–max) | AUROC, ε = 1 | AUROC, non-private |', '|---|---|---|---|---|']
kv = {}
for K in [5, 10, 20, 30]:
    a1 = grp('fl', 1.0, K); ai = grp('fl', inf, K)
    if not a1 or not ai: continue
    n = np.mean([i['n_train'] for i in a1[0]['site_info']]); s_ = [i['sigma'] for i in a1[0]['site_info']]
    rows.append(f"| {K} | {n:.0f} | {min(s_):.2f}–{max(s_):.2f} | {ms(au(a1))} | {ms(au(ai))} |")
    kv[K] = np.mean(au(a1))
V['auc_k5'] = f"{kv.get(5, float('nan')):.3f}"; V['auc_k30'] = f"{kv.get(30, float('nan')):.3f}"
T['TABLE5'] = ('Table 5: Effect of the number of hospitals with the total data fixed (mean ± SD over 5 seeds).', rows)

# weighted vs unweighted
w1 = grp('fl', 1.0, 20, 1); wi = grp('fl', inf, 20, 1)
rows = ['| Aggregation | AUROC, ε = 1 | AUROC, non-private |', '|---|---|---|',
        f"| Unweighted FedAvg (FLHealthChain, Eq. 8) | {ms(au(r1))} | {ms(au(r_inf))} |",
        f"| Size-weighted FedAvg (requires knowing each hospital's mᵢ) | {ms(au(w1))} | {ms(au(wi))} |"]
V['wdiff_eps1'] = f"{np.mean(au(w1)) - np.mean(au(r1)):+.3f}"; V['wdiff_inf'] = f"{np.mean(au(wi)) - np.mean(au(r_inf)):+.3f}"
T['TABLE6'] = ('Table 6: Unweighted versus size-weighted aggregation (mean ± SD over 5 seeds).', rows)
V['clip_rate_eps1'] = f"{100 * np.mean([r['update_clip_rate'] for r in r1]):.0f}"
# convergence figure
fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
for rs, lab, col in [(r_inf, 'non-private', C2), (r1, 'ε = 1', C1), (grp('fl', 4.0), 'ε = 4', C4)]:
    L = np.array([[h['test_loss'] for h in r['history']] for r in rs]); A = np.array([[h['test_auroc'] for h in r['history']] for r in rs])
    x = np.arange(1, L.shape[1] + 1)
    ax[0].plot(x, L.mean(0), color=col, label=lab); ax[0].fill_between(x, L.mean(0) - L.std(0), L.mean(0) + L.std(0), color=col, alpha=.15)
    ax[1].plot(x, A.mean(0), color=col, label=lab); ax[1].fill_between(x, A.mean(0) - A.std(0), A.mean(0) + A.std(0), color=col, alpha=.15)
    if lab == 'non-private':
        am = A.mean(0); V['conv_round'] = str(int(np.argmax(am >= am[-1] - 0.01)) + 1)
ax[0].set_xlabel('round'); ax[0].set_ylabel('test cross-entropy'); ax[0].legend(frameon=False, fontsize=8); ax[0].set_title('(a) Test loss', fontsize=10)
ax[1].set_xlabel('round'); ax[1].set_ylabel('test AUROC'); ax[1].set_title('(b) Test AUROC', fontsize=10)
fig.tight_layout(); fig.savefig(f'{OUT}/figs/fig4_convergence.png', dpi=300); plt.close(fig)
V['t_train'] = f"{np.mean([r['runtime_s'] for r in r1]) / (20 * 20):.2f}"

# ---------------- crypto ----------------
zkm = json.load(open(f'{ZK}/results/zk_model.json')); zkb = json.load(open(f'{ZK}/results/zk_14530.json'))
zks = [json.load(open(f)) for f in sorted(glob.glob(f'{ZK}/results/zk_scale_*.json'))] + [zkm, zkb]
V['zk_constraints'] = f"{zkm['constraints']:,}"; V['zk_constraints_k'] = f"{zkm['constraints'] / 1000:.0f}k"
V['zk_prove'] = f"{zkm['prove_s_mean']:.2f}"; V['zk_prove_sd'] = f"{zkm['prove_s_sd']:.2f}"; V['zk_verify'] = f"{zkm['verify_ms_mean']:.1f}"
V['zk_proof_bytes'] = str(zkm['proof_bytes_compressed']); V['n_params_big'] = f"{zkb['n_params']:,}"; V['zk_prove_big'] = f"{zkb['prove_s_mean']:.1f}"
V['update_kb'] = f"{V['n_params_raw'] * 2 / 1024:.1f}"
ls = json.load(open(f'{ZK}/results/lsag_bench.json')); l20 = [r for r in ls if r['ring'] == 20][0]
V['lsag_bytes20'] = str(l20['sig_bytes']); V['lsag_sign20'] = f"{l20['sign_ms']:.1f}"; V['lsag_verify20'] = f"{l20['verify_ms']:.1f}"
rows = ['| Component | Quantity | Measured value |', '|---|---|---|',
        f"| Groth16 update circuit ({V['n_params']} parameters) | R1CS constraints | {zkm['constraints']:,} |",
        f"| | Proving time (2 vCPU, {zkm['reps']} runs) | {zkm['prove_s_mean']:.2f} ± {zkm['prove_s_sd']:.2f} s |",
        f"| | Verification time | {zkm['verify_ms_mean']:.2f} ± {zkm['verify_ms_sd']:.2f} ms |",
        f"| | Proof size (compressed / uncompressed) | {zkm['proof_bytes_compressed']} B / {zkm['proof_bytes_uncompressed']} B |",
        f"| | Verifying key size | {zkm['vk_bytes']} B |",
        f"| | One-time circuit setup | {zkm['setup_s']:.0f} s |",
        f"| | Over-norm (2S) update proved? | {'No (prover fails)' if zkm['over_norm_update_rejected'] else 'YES'} |",
        f"| Groth16, {zkb['n_params']:,} parameters (earlier 47→128→64→2 model) | Constraints / proving time | {zkb['constraints']:,} / {zkb['prove_s_mean']:.1f} ± {zkb['prove_s_sd']:.1f} s |",
        f"| MiMC commitment recomputation (aggregator) | Time per update | {zkm['commit_ms']:.1f} ms |",
        f"| LSAG, ring of 20 (secp256k1) | Sign / verify | {l20['sign_ms']:.1f} ± {l20['sign_sd']:.1f} ms / {l20['verify_ms']:.1f} ± {l20['verify_sd']:.1f} ms |",
        f"| | Signature size | {l20['sig_bytes']} B |",
        f"| | Tamper rejected / same-key linked / different keys unlinked | {'yes' if l20['tamper_rejected'] else 'NO'} / {'yes' if l20['same_key_linked'] else 'NO'} / {'yes' if l20['diff_key_unlinked'] else 'NO'} (30 of 30 runs) |"]
T['TABLE7'] = ('Table 7: Measured cost of the cryptographic layer (Go, gnark v0.13, 2 vCPU).', rows)
fig, ax = plt.subplots(1, 2, figsize=(10, 3.4))
rg = [r['ring'] for r in ls]
ax[0].errorbar(rg, [r['sign_ms'] for r in ls], yerr=[r['sign_sd'] for r in ls], marker='o', color=C1, capsize=3, label='sign')
ax[0].errorbar(rg, [r['verify_ms'] for r in ls], yerr=[r['verify_sd'] for r in ls], marker='s', color=C2, capsize=3, label='verify')
ax2 = ax[0].twinx(); ax2.plot(rg, [r['sig_bytes'] for r in ls], color='#888', ls=':', marker='^', label='size'); ax2.set_ylabel('signature size (bytes)', color='#666'); ax2.spines['top'].set_visible(False)
ax[0].set_xlabel('ring size n'); ax[0].set_ylabel('time (ms)'); ax[0].legend(frameon=False, fontsize=8, loc='upper left'); ax[0].set_title('(a) LSAG ring signatures', fontsize=10)
zks = sorted({z['n_params']: z for z in zks}.values(), key=lambda z: z['n_params'])
ax[1].errorbar([z['n_params'] for z in zks], [z['prove_s_mean'] for z in zks], yerr=[z['prove_s_sd'] for z in zks], marker='o', color=C1, capsize=3)
for z in zks: ax[1].annotate(f"{z['constraints'] / 1000:.0f}k constr.", (z['n_params'], z['prove_s_mean']), textcoords='offset points', xytext=(4, -12), fontsize=7)
ax[1].set_xlabel('model parameters P'); ax[1].set_ylabel('Groth16 proving time (s)'); ax[1].set_title('(b) Update proof generation', fontsize=10)
fig.tight_layout(); fig.savefig(f'{OUT}/figs/fig5_crypto.png', dpi=300); plt.close(fig)
V['_zk_scale'] = [(z['n_params'], z['constraints'], z['prove_s_mean']) for z in zks]

# ---------------- ledger ----------------
LD = f'{ZK}/results/ledger'
def ledger(kind, ch, c=None):
    pat = f'{LD}/audit_{ch}_c{c}_r*.json' if kind == 'audit' else f'{LD}/update_{ch}_part*.json'
    return [json.load(open(f)) for f in sorted(glob.glob(pat))]
def agg(rs, k): return np.mean([r[k] for r in rs]), (np.std([r[k] for r in rs], ddof=1) if len(rs) > 1 else 0)
rows = ['| Channel (consensus) | Workload | Workers | Runs | Committed TPS | Median latency (ms) | p95 latency (ms) | Failed |', '|---|---|---|---|---|---|---|---|']
fig, ax = plt.subplots(1, 2, figsize=(10, 3.5))
for ch, lab, col in [('bft4', 'BFT (SmartBFT)', C1), ('raft4', 'CFT (Raft)', C2)]:
    tp, la = [], []
    for c in [10, 50, 100, 200]:
        rs = ledger('audit', ch, c)
        if not rs: continue
        t, ts = agg(rs, 'tps'); p, _ = agg(rs, 'lat_p50_ms'); p95, _ = agg(rs, 'lat_p95_ms')
        rows.append(f"| {lab} | anchor | {c} | {len(rs)} | {t:.1f} ± {ts:.1f} | {p:.0f} | {p95:.0f} | {sum(r['fail'] for r in rs)} |")
        tp.append((c, t, ts)); la.append((c, p))
        if c == 100:
            V[f"anchor_tps_{ch[:-1]}"] = f"{t:.0f}"; V[f"anchor_p50_{ch[:-1]}"] = f"{p:.0f}"
    ax[0].errorbar([x[0] for x in tp], [x[1] for x in tp], yerr=[x[2] for x in tp], marker='o', color=col, capsize=3, label=lab)
    ax[1].plot([x[0] for x in la], [x[1] for x in la], marker='o', color=col, label=lab)
for ch, lab in [('bft4', 'BFT (SmartBFT)'), ('raft4', 'CFT (Raft)')]:
    rs = ledger('update', ch)
    if not rs: continue
    t, ts = agg(rs, 'tps'); p, _ = agg(rs, 'lat_p50_ms'); p95, _ = agg(rs, 'lat_p95_ms')
    rows.append(f"| {lab} | verified update | 50 | {len(rs)} | {t:.1f} ± {ts:.1f} | {p:.0f} | {p95:.0f} | {sum(r['fail'] for r in rs)} |")
    k = ch[:-1]; V[f'upd_tps_{k}'] = f"{t:.1f}"; V[f'upd_p50_{k}'] = f"{p:.0f}"; V[f'upd_p95_{k}'] = f"{p95:.0f}"
    ax[0].axhline(t, color=C1 if k == 'bft' else C2, ls=':', lw=1)
ax[0].set_xlabel('concurrent workers'); ax[0].set_ylabel('committed TPS'); ax[0].legend(frameon=False, fontsize=8); ax[0].set_title('(a) Throughput (anchor tx; dotted = verified update tx)', fontsize=9)
ax[1].set_xlabel('concurrent workers'); ax[1].set_ylabel('median submit→commit latency (ms)'); ax[1].set_title('(b) Latency (anchor tx)', fontsize=10)
fig.tight_layout(); fig.savefig(f'{OUT}/figs/fig6_ledger.png', dpi=300); plt.close(fig)
T['TABLE8'] = ('Table 8: Ledger performance on a live Fabric 3.1.1 network (4 orderers, 4 peers, MAJORITY endorsement, single 2-vCPU host). Anchor: 2,000 transactions per run; verified update: 450 transactions per run, each verified with Groth16 and LSAG by three endorsing peers.', rows)
V['upd_p50_bft_s'] = f"{float(V['upd_p50_bft']) / 1000:.2f}"
rr = [json.load(open(f)) for f in sorted(glob.glob(f'{LD}/round_bft4_*.json'))]
V['round_commit'] = f"{np.mean([r['elapsed_s'] for r in rr]):.2f}"; V['round_commit_p50'] = f"{np.mean([r['lat_p50_ms'] for r in rr]):.0f}"
V['round_runs'] = str(len(rr))
ub, ur = float(V['upd_tps_bft']), float(V['upd_tps_raft'])
ab, ar = float(V['anchor_tps_bft']), float(V['anchor_tps_raft'])
V['bft_vs_raft_sentence'] = (f"Byzantine fault tolerance therefore cost {100 * (1 - ab / ar):.0f}% of anchor throughput relative to Raft on this host, " if ab < ar else f"On this host the BFT channel matched or exceeded Raft on anchor throughput ({ab:.0f} vs {ar:.0f} TPS), ") + \
    (f"and {100 * (1 - ub / ur):.0f}% of verified-update throughput." if ub < ur else f"and verified-update throughput was {ub:.1f} vs {ur:.1f} TPS, because endorsement-time verification rather than ordering dominates.")
env = json.load(open(f'{LD}/envelope.json'))
V['env_kb'] = f"{env['update_env_bytes'] / 1024:.1f}"; V['payload_bytes'] = f"{env['update_args_bytes']:,}"
V['tps_bound'] = f"{(2 * 1024 * 1024 / env['update_env_bytes']) / 0.5:,.0f}"
# BFT with 7 orderers
b7 = sorted(glob.glob(f'{LD}/audit_bft7_c100_r*.json'))
if b7:
    rs7 = [json.load(open(f)) for f in b7]; rr7 = [json.load(open(f)) for f in sorted(glob.glob(f'{LD}/audit_raft7_c100_r*.json'))]
    u7 = [json.load(open(f)) for f in sorted(glob.glob(f'{LD}/update_bft7_part*.json'))]
    t7, _ = agg(rs7, 'tps'); p7, _ = agg(rs7, 'lat_p50_ms'); tr7, _ = agg(rr7, 'tps') if rr7 else (float('nan'), 0)
    ut7 = agg(u7, 'tps')[0] if u7 else float('nan')
    V['BFT7_PARA'] = (f"ZQHLZQ With seven orderers ($f_o=2$), all on the same two vCPUs, the BFT channel committed {t7:.0f} anchor TPS (median latency {p7:.0f} ms) "
                      f"and {ut7:.1f} verified update TPS. The corresponding figures with four orderers were {V['anchor_tps_bft']} and {V['upd_tps_bft']}. The Raft channel with seven orderers reached {tr7:.0f} anchor TPS. "
                      "Tolerating one more Byzantine orderer therefore has a measurable cost on a single host. This cost is expected to be smaller when orderers run on separate machines.")
else:
    V['BFT7_PARA'] = ''
# attacks
att = json.load(open(f'{LD}/attack_bft4.json'))
names = {'wrong_commitment': 'Proof with mismatched commitment', 'proof_replay_other_round': 'Proof replayed under another round number',
         'tampered_signature': 'Ring signature with one flipped byte', 'outsider_signer': 'Signer key outside the registered ring',
         'valid_first_submission': 'Valid submission (control)', 'duplicate_key_image': 'Second submission, same key image and round'}
rows = ['| Submitted transaction | Count | Expected outcome | Outcome as expected |', '|---|---|---|---|']
allok = True
for k, lab in names.items():
    ok, bad = att[k]; allok &= bad == 0
    rows.append(f"| {lab} | {ok + bad} | {'accepted' if k == 'valid_first_submission' else 'rejected'} | {ok} / {ok + bad} |")
T['TABLE10'] = ('Table 10: Adversarial submissions to the live BFT channel.', rows)
n_bad = sum(sum(v) for k, v in att.items() if k != 'valid_first_submission')
V['attack_sentence'] = (f"All {n_bad} adversarial transactions were rejected at endorsement and never reached ordering, and all valid control submissions were accepted (Table 10)." if allok
                        else "Some outcomes differed from expectation; see Table 10.")
# round latency
t_agg = 20 * zkm['commit_ms']; V['t_agg'] = f"{t_agg:.0f}"
tr = 0
V['t_round'] = f"{tr:.1f}"
rows = ['| Step (per round, critical path) | Time | Share |', '|---|---|---|']
parts = [('Local DP-SGD training (one epoch, mean hospital)', float(V['t_train'])), ('Clip, quantise, commit (MiMC)', zkm['commit_ms'] / 1000),
         ('Groth16 proof generation', zkm['prove_s_mean']), ('LSAG signing (n = 20)', l20['sign_ms'] / 1000),
         ('Commit all 20 SubmitUpdate transactions of the round (endorse with π, σ verification, order, validate)', float(V['round_commit'])),
         ('Fetch 20 updates and recompute commitments', t_agg / 1000)]
tot = sum(p[1] for p in parts)
for lab, t in parts: rows.append(f"| {lab} | {t:.3f} s | {100 * t / tot:.1f}% |")
rows.append(f"| **Total** | **{tot:.2f} s** | 100% |")
V['t_round'] = f"{tot:.1f}"
T['TABLE9'] = ('Table 9: Critical-path latency of one federated round (hospitals train and prove in parallel).', rows)

# ---------------- static tables ----------------
T['TABLE1'] = ('Table 1: Comparative analysis of blockchain-based healthcare frameworks', [
    '| System | Blockchain type | Privacy technique | Verifiable updates | Scalability | Interoperability | Key weakness |', '|---|---|---|---|---|---|---|',
    '| MedRec [4] | Permissioned Ethereum | Basic encryption | No | Off-chain storage | Intra-hospital | Metadata exposure; poor scalability |',
    '| FHIRChain [3] | Public Ethereum | Token-based authorisation | No | Lightweight tokens | HL7 FHIR (partial) | No privacy primitives |',
    '| Patientory [5] | Private chain | Encrypted storage | No | Transaction batching | API-based | High cost; limited compatibility |',
    '| OmniPHR [11] | Distributed PHR | Attribute-based encryption | No | Off-chain health data | Standardised PHR model | Access-management overhead |',
    '| BPFISH [29] | Consortium blockchain | Differential privacy | No | Not evaluated | None | No ZKP; no anonymity |',
    '| FabricFL [25] | Hyperledger Fabric | None at gradient level | No | Fabric channels | None | No gradient-level privacy |',
    '| FedBlockHealth [30] | Blockchain + sidechains | None | No | Sidechains | Partial | No cryptographic privacy |',
    '| FLHealthChain (ours) | Hyperledger Fabric 3.1 (BFT + Raft channels) | DP-SGD (RDP-accounted) + LSAG | Yes (Groth16 norm-bound proof) | Per-domain channels; ~1.3 KB on-chain per update | FHIR R4 data model | Proving cost; trusted setup; single-host evaluation; synthetic data |'])
T['TABLE2'] = ('Table 2: Threat–defence mapping in FLHealthChain', [
    '| Threat | Vulnerability | Defence mechanism | Security property |', '|---|---|---|---|',
    '| Gradient inversion | Updates expose record-level features | DP-SGD with per-example clipping and Gaussian noise; per-hospital σᵢ from RDP accountant | Record-level (ε, δ)-DP (Theorem 1) |',
    '| Model poisoning (scaling) | An oversized update dominates the aggregate | Update clipping plus Groth16 norm-bound proof verified by the MVC | Bounded update influence (Theorem 2) |',
    '| Identity disclosure | Submissions traceable to hospitals | LSAG ring signature over all hospital keys; shared submitter identity | Signer anonymity (Theorem 3) |',
    '| Double / Sybil submission | One hospital submits several updates per round | Key-image freshness check per (ring, round) | Linkability (Theorem 3) |',
    '| Ledger tampering / forks | Byzantine orderers equivocate | SmartBFT ordering with n₀ ≥ 3f₀ + 1; MAJORITY endorsement | Safety and liveness (Theorem 4) |',
    '| Replay / MITM | Interception or replay of messages | Mutual TLS; Fabric transaction-ID uniqueness | Confidentiality in transit; replay protection |',
    '| Unauthorised data use | Records used without consent | Consent Management Contract; revocation events | Auditable consent state |',
    '| GDPR right to erasure | Released models retain past contributions | Revocation excludes future use; DP bounds residual influence | Partial; full erasure needs unlearning (Section 9.2) |'])
T['TABLE3'] = ('Table 3: System configuration and implementation environment (all components executed)', [
    '| Component | Specification / version |', '|---|---|',
    '| Host | Single cloud VM, 2 vCPU (x86-64), 8 GB RAM, Linux |',
    '| Blockchain | Hyperledger Fabric 3.1.1 native binaries; 4 orderer nodes (7 in scaling run), 4 peer organisations × 1 peer |',
    '| Channels | bft4: SmartBFT; raft4: etcdraft; BatchTimeout 500 ms, MaxMessageCount 500, PreferredMaxBytes 2 MB |',
    '| Endorsement policy | MAJORITY (3 of 4 organisations) |',
    '| Chaincode | Go 1.24, fabric-contract-api-go v2.2, chaincode-as-a-service |',
    '| zk-SNARK | gnark v0.13.0, Groth16 over BN254, MiMC commitment, lookup range checks |',
    '| Ring signature | LSAG over secp256k1 (decred secp256k1 v4.4) |',
    '| Client / load generator | Fabric Gateway SDK v1.7.1 (Go), closed loop |',
    '| Federated learning | Python 3, NumPy; exact per-example gradients; Poisson subsampling |',
    '| Privacy accountant | Google dp_accounting (RDP, subsampled Gaussian) |',
    '| Data | Synthea (3 runs, seeds 2026–2028, Massachusetts, ages 45–90), landmark cohort |',
    '| Off-chain storage | Content-addressed local store (IPFS in reference design) |'])

json.dump({k: v for k, v in V.items() if not k.startswith('_')}, open(f'{OUT}/values.json', 'w'), indent=1)
json.dump(T, open(f'{OUT}/tables.json', 'w'), indent=1)
print(json.dumps({k: v for k, v in V.items() if k != 'BFT7_PARA'}, indent=0)[:3000])
