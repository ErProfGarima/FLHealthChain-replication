import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
plt.rcParams['font.family'] = 'DejaVu Sans'
OUT = '/home/claude/flhc/paper/figs/'
PAL = [('#d6ebe7', '#5f9e95'), ('#e3e0f0', '#8277b3'), ('#f6ded8', '#c46a57'), ('#dbe5f0', '#5b7fa8'), ('#f4ebd7', '#b8964e')]

def box(ax, x, y, w, h, fc, ec, lw=1.2, r=0.02):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f'round,pad=0,rounding_size={r}', fc=fc, ec=ec, lw=lw))

def fig1():
    layers = [
        ('Layer 1 · User interaction', ['Patients\nconsent grant / revoke', 'Clinicians\ndata requests', 'Researchers\nmodel queries', 'mTLS gRPC / REST\nAPI gateway']),
        ('Layer 2 · Federated learning', ['Local DP-SGD\nper-example clip C, Poisson q', 'Update clip ‖Δ‖₂ ≤ S\n16-bit quantisation', 'Unweighted FedAvg\n(anonymous updates)']),
        ('Layer 3 · Privacy & integrity', ['Gaussian mechanism\n(ε, δ)-DP via RDP accountant', 'Groth16 zk-SNARK (BN254)\nnorm bound + MiMC commitment', 'LSAG ring signature\nsecp256k1 · key-image linkability']),
        ('Layer 4 · Blockchain execution (Hyperledger Fabric 3.1)', ['BFT channel (SmartBFT)\nupdates · consent · audit', 'Raft channel (CFT)\nIoMT telemetry anchors', 'Chaincode\nMVC · CMC · ATC\nverifies π, σ', 'Off-chain store\n(content-addressed\nupdate vectors)']),
        ('Layer 5 · Interoperability', ['HL7 FHIR R4 resources\n(Synthea-native)', 'Feature extraction\nFHIR → model input', 'Cross-network relay\n(future work)'])]
    fig, ax = plt.subplots(figsize=(10, 8.6)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    H = 0.165; gap = 0.04; y = 1 - H - 0.005
    for li, (title, items) in enumerate(layers):
        fc, ec = PAL[li]
        box(ax, 0.02, y, 0.96, H, fc, ec, 1.6)
        ax.text(0.5, y + H - 0.03, title, ha='center', va='center', fontsize=12.5, weight='bold', color='#222')
        n = len(items); iw = (0.92 - 0.02 * (n - 1)) / n
        for k, it in enumerate(items):
            x = 0.04 + k * (iw + 0.02)
            dashed = 'future' in it
            ax.add_patch(FancyBboxPatch((x, y + 0.018), iw, H - 0.075, boxstyle='round,pad=0,rounding_size=0.012',
                                        fc='white', ec=ec, lw=1.0, ls='--' if dashed else '-', alpha=0.95))
            ax.text(x + iw / 2, y + 0.018 + (H - 0.075) / 2, it, ha='center', va='center', fontsize=9.3 if n < 4 else 8.8, color='#555' if dashed else '#111')
        if li < len(layers) - 1:
            ax.add_patch(FancyArrowPatch((0.5, y - 0.002), (0.5, y - gap + 0.002), arrowstyle='<|-|>', mutation_scale=12, color='#444', lw=1.2))
        y -= H + gap
    fig.savefig(OUT + 'fig1_architecture.png', dpi=300, bbox_inches='tight'); plt.close(fig)

def fig2():
    steps = [
        ('① Patient consent', 'GrantConsent on BFT channel · revocation excludes records from later rounds', PAL[0]),
        ('② Local DP-SGD', 'Poisson sampling q = B/mᵢ · per-example clip C = 1 · Gaussian noise σᵢ chosen by RDP accountant', PAL[1]),
        ('③ Clip, quantise, commit', 'Δ clipped to ‖Δ‖₂ ≤ S · 16-bit fixed point · c = MiMC(t ‖ pack(Δ))', PAL[1]),
        ('④ Groth16 proof π', 'proves ‖Δ‖₂ ≤ S and that c opens to Δ · constant 196-byte proof', PAL[2]),
        ('⑤ LSAG ring signature σ', 'signs (t, ring, c, H(π)) over all n hospital keys · key image I · 705 B for n = 20', PAL[2]),
        ('⑥ SubmitUpdate (BFT channel)', 'endorsers verify π and σ, reject reused (ring, t, I) · ~1.3 KB evidence stored on-chain', PAL[3]),
        ('⑦ Aggregate and redistribute', 'fetch Δ off-chain, recompute c · unweighted FedAvg · anchor H(wₜ₊₁) on-chain', PAL[4])]
    fig, ax = plt.subplots(figsize=(10, 8)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    h = 0.105; g = 0.032; y = 1 - h - 0.005
    for i, (t, d, (fc, ec)) in enumerate(steps):
        box(ax, 0.03, y, 0.84, h, fc, ec, 1.5)
        ax.text(0.45, y + h * 0.66, t, ha='center', va='center', fontsize=12.5, weight='bold')
        ax.text(0.45, y + h * 0.30, d, ha='center', va='center', fontsize=9.4)
        if i < len(steps) - 1:
            ax.add_patch(FancyArrowPatch((0.45, y), (0.45, y - g), arrowstyle='-|>', mutation_scale=14, color='#333', lw=1.3))
        if i == 1: y2 = y + h / 2
        if i == len(steps) - 1: y7 = y + h / 2
        y -= h + g
    ax.add_patch(FancyArrowPatch((0.87, y7), (0.87, y2), connectionstyle='arc3,rad=0.22', arrowstyle='-|>', mutation_scale=14, color='#333', lw=1.3))
    ax.text(1.0, (y2 + y7) / 2, 'next round', rotation=270, va='center', ha='center', fontsize=11)
    fig.savefig(OUT + 'fig2_lifecycle.png', dpi=300, bbox_inches='tight'); plt.close(fig)

def fig7():
    rows = [('Gradient inversion\nHBC adversaries', 'DP-SGD (Gaussian mechanism)\nper-hospital σᵢ from RDP accountant', 'Record-level (ε, δ)-DP\nTheorem 1'),
            ('Model poisoning (scaling)\nByzantine hospitals', 'Groth16 norm-bound proof\nverified by MVC at endorsement', 'Bounded update influence\nTheorem 2 (trusted setup)'),
            ('Identity disclosure\nreplay / Sybil submission', 'LSAG ring signature\nkey-image freshness check', 'Anonymity (DDH, ROM) + linkability\nTheorem 3'),
            ('Ledger forks / tampering\nByzantine orderers', 'SmartBFT ordering, n₀ ≥ 3f₀+1\nMAJORITY endorsement', 'Safety & liveness\nTheorem 4'),
            ('Eavesdropping / MITM\nexternal adversaries', 'Mutual TLS (ECDHE, AES-GCM)\nFabric TxID uniqueness', 'Confidentiality in transit\nreplay protection'),
            ('Unauthorised data use\nconsent violations', 'Consent Management Contract\nrevocation events', 'Auditable consent state\n(not unlearning; §9.2)')]
    fig, ax = plt.subplots(figsize=(11, 7.4)); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis('off')
    cols = [(0.01, 'Threats', ('#f6d5d3', '#b75b56')), (0.355, 'Defence mechanisms', ('#dbe5f0', '#5b7fa8')), (0.70, 'Property guaranteed', ('#dcebdc', '#5e9a64'))]
    w = 0.29
    for x, t, (fc, ec) in cols:
        box(ax, x, 0.925, w, 0.06, ec, ec); ax.text(x + w / 2, 0.955, t, ha='center', va='center', color='white', fontsize=13, weight='bold')
    h = 0.12; y = 0.79
    for r in rows:
        for k, (x, _, (fc, ec)) in enumerate(cols):
            box(ax, x, y, w, h, fc, ec, 1.4); ax.text(x + w / 2, y + h / 2, r[k], ha='center', va='center', fontsize=9.0)
            if k < 2:
                ax.add_patch(FancyArrowPatch((x + w + 0.004, y + h / 2), (cols[k + 1][0] - 0.004, y + h / 2), arrowstyle='-|>', mutation_scale=12, color='#555'))
        y -= h + 0.028
    fig.savefig(OUT + 'fig7_threatmap.png', dpi=300, bbox_inches='tight'); plt.close(fig)

fig1(); fig2(); fig7(); print('ok')
