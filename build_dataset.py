"""Landmark 12-month admission-or-death cohort from Synthea CSV export.
Landmark L = (last date in export) - 365 days.  Cohort: alive at L, >=1 encounter in [L-730d, L].
Features are computed only from data dated <= L; label = death in (L, L+365d].
Hospitals: k-means (k=20) on residence coordinates -> regional sites (natural non-IID split)."""
import sys, json, numpy as np, pandas as pd
from sklearn.cluster import KMeans

src, out = sys.argv[1], sys.argv[2]
K = int(sys.argv[3]) if len(sys.argv) > 3 else 20
P = pd.read_csv(f'{src}/patients.csv', usecols=['Id','BIRTHDATE','DEATHDATE','GENDER','LAT','LON'])
E = pd.read_csv(f'{src}/encounters.csv', usecols=['START','PATIENT','ENCOUNTERCLASS'])
E['START'] = pd.to_datetime(E.START, utc=True).dt.tz_localize(None)
end = E.START.max().normalize()
L = end - pd.Timedelta(days=365)
W0 = L - pd.Timedelta(days=730)
P['BIRTHDATE'] = pd.to_datetime(P.BIRTHDATE); P['DEATHDATE'] = pd.to_datetime(P.DEATHDATE)
alive = P[(P.DEATHDATE.isna()) | (P.DEATHDATE > L)].copy()
Ew = E[(E.START > W0) & (E.START <= L)]
alive = alive[alive.Id.isin(Ew.PATIENT.unique())]
alive['age'] = (L - alive.BIRTHDATE).dt.days / 365.25
alive = alive[alive.age >= 18].set_index('Id')
ids = alive.index
X = pd.DataFrame(index=ids)
X['age'] = alive.age
X['male'] = (alive.GENDER == 'M').astype(float)
H = L + pd.Timedelta(days=365)
died = (alive.DEATHDATE > L) & (alive.DEATHDATE <= H)
acute = E[(E.START > L) & (E.START <= H) & E.ENCOUNTERCLASS.isin(['inpatient'])].PATIENT.unique()
y = (died | alive.index.isin(acute)).astype(int)   # 12-month inpatient admission or death
y_death = died.astype(int)

# observations (latest value <= L within feature window)
OBS = {'8480-6':'sbp','8462-4':'dbp','8867-4':'hr','9279-1':'rr','39156-5':'bmi','29463-7':'weight',
       '72514-3':'pain','33914-3':'egfr','38483-4':'creatinine','2339-0':'glucose','4548-4':'hba1c',
       '6299-2':'bun','2947-0':'sodium','6298-4':'potassium','2069-3':'chloride','20565-8':'co2',
       '49765-1':'calcium','2093-3':'chol_total','18262-6':'ldl','2085-9':'hdl','2571-8':'trig',
       '718-7':'hemoglobin','6690-2':'wbc','777-3':'platelets','55758-7':'phq2'}
chunks = []
for ch in pd.read_csv(f'{src}/observations.csv', usecols=['DATE','PATIENT','CODE','VALUE','TYPE'], chunksize=2_000_000):
    ch = ch[ch.CODE.isin(OBS.keys()) & ch.PATIENT.isin(ids) & (ch.TYPE == 'numeric')]
    ch['DATE'] = pd.to_datetime(ch.DATE, utc=True).dt.tz_localize(None)
    ch = ch[(ch.DATE > W0) & (ch.DATE <= L)]
    chunks.append(ch)
O = pd.concat(chunks)
O['VALUE'] = pd.to_numeric(O.VALUE, errors='coerce')
O = O.sort_values('DATE').groupby(['PATIENT','CODE']).VALUE.last().unstack()
for c, n in OBS.items():
    X[n] = O[c].reindex(ids) if c in O.columns else np.nan
# smoking
sm = []
for ch in pd.read_csv(f'{src}/observations.csv', usecols=['DATE','PATIENT','CODE','VALUE'], chunksize=2_000_000):
    ch = ch[(ch.CODE == '72166-2') & ch.PATIENT.isin(ids)]
    ch['DATE'] = pd.to_datetime(ch.DATE, utc=True).dt.tz_localize(None)
    sm.append(ch[ch.DATE <= L])
S = pd.concat(sm).sort_values('DATE').groupby('PATIENT').VALUE.last()
X['smoker'] = S.reindex(ids).fillna('').str.contains('every day|some day', case=False).astype(float)
# utilisation in prior 365 days
E1 = E[(E.START > L - pd.Timedelta(days=365)) & (E.START <= L) & E.PATIENT.isin(ids)]
for cls in ['inpatient','emergency','urgentcare','ambulatory','outpatient','wellness','snf','hospice','home']:
    X[f'n_{cls}'] = E1[E1.ENCOUNTERCLASS == cls].groupby('PATIENT').size().reindex(ids).fillna(0)
# longer-horizon utilisation, recency and cost
E2 = E[(E.START > W0) & (E.START <= L) & E.PATIENT.isin(ids)]
for cls in ['inpatient', 'emergency']:
    X[f'n_{cls}_2y'] = E2[E2.ENCOUNTERCLASS == cls].groupby('PATIENT').size().reindex(ids).fillna(0)
acute_prior = E2[E2.ENCOUNTERCLASS.isin(['inpatient', 'emergency', 'urgentcare'])]
last_acute = acute_prior.groupby('PATIENT').START.max().reindex(ids)
X['days_since_acute'] = ((L - last_acute).dt.days).fillna(730).clip(0, 730)
X['n_encounters_90d'] = E[(E.START > L - pd.Timedelta(days=90)) & (E.START <= L) & E.PATIENT.isin(ids)].groupby('PATIENT').size().reindex(ids).fillna(0)
EC = pd.read_csv(f'{src}/encounters.csv', usecols=['START', 'PATIENT', 'TOTAL_CLAIM_COST'])
EC['START'] = pd.to_datetime(EC.START, utc=True).dt.tz_localize(None)
EC = EC[(EC.START > L - pd.Timedelta(days=365)) & (EC.START <= L) & EC.PATIENT.isin(ids)]
X['n_claim_cost_1y'] = EC.groupby('PATIENT').TOTAL_CLAIM_COST.sum().reindex(ids).fillna(0)
PR = pd.read_csv(f'{src}/procedures.csv', usecols=['START', 'PATIENT'])
PR['START'] = pd.to_datetime(PR.START, utc=True).dt.tz_localize(None)
PR = PR[(PR.START > L - pd.Timedelta(days=365)) & (PR.START <= L) & PR.PATIENT.isin(ids)]
X['n_procedures_1y'] = PR.groupby('PATIENT').size().reindex(ids).fillna(0)
CP = pd.read_csv(f'{src}/careplans.csv', usecols=['START', 'STOP', 'PATIENT'])
CP['START'] = pd.to_datetime(CP.START); CP['STOP'] = pd.to_datetime(CP.STOP)
CP = CP[CP.PATIENT.isin(ids) & (CP.START <= L) & (CP.STOP.isna() | (CP.STOP > L))]
X['n_active_careplans'] = CP.groupby('PATIENT').size().reindex(ids).fillna(0)
# active conditions at L
C = pd.read_csv(f'{src}/conditions.csv', usecols=['START','STOP','PATIENT','DESCRIPTION'])
C = C[C.PATIENT.isin(ids)]
C['START'] = pd.to_datetime(C.START); C['STOP'] = pd.to_datetime(C.STOP)
C = C[(C.START <= L) & (C.STOP.isna() | (C.STOP > L))]
FLAGS = {'diabetes':'diabetes','hypertension':'hypertension','heart_failure':'heart failure',
         'copd':'chronic obstructive|pulmonary emphysema','ckd':'chronic kidney','dementia':'alzheimer|dementia',
         'afib':'atrial fibrillation','ihd':'ischemic heart|myocardial infarction|coronary',
         'cancer':'neoplasm|carcinoma|cancer','stroke':'stroke|cerebrovascular','anemia':'anemia',
         'obesity':'obesity|body mass index 30','osteoporosis':'osteoporosis','sepsis':'sepsis'}
d = C.DESCRIPTION.str.lower()
for k, pat in FLAGS.items():
    X[f'dx_{k}'] = C[d.str.contains(pat, regex=True)].groupby('PATIENT').size().reindex(ids).fillna(0).clip(0, 1)
X['n_active_conditions'] = C.groupby('PATIENT').size().reindex(ids).fillna(0)
M = pd.read_csv(f'{src}/medications.csv', usecols=['START','STOP','PATIENT'])
M = M[M.PATIENT.isin(ids)]
M['START'] = pd.to_datetime(M.START, utc=True).dt.tz_localize(None); M['STOP'] = pd.to_datetime(M.STOP, utc=True).dt.tz_localize(None)
M = M[(M.START <= L) & (M.STOP.isna() | (M.STOP > L))]
X['n_active_meds'] = M.groupby('PATIENT').size().reindex(ids).fillna(0)
# hospitals
coords = alive[['LAT','LON']].values
km = KMeans(n_clusters=K, n_init=10, random_state=0).fit(coords)
site = pd.Series(km.labels_, index=ids)
X = X.astype(float)
alive[['LAT','LON']].to_csv(f'{out.rsplit("/",1)[0] if "/" in out else "."}/coords.csv')
X.to_csv(f'{out}_X.csv'); y.to_csv(f'{out}_y.csv'); site.to_csv(f'{out}_site.csv')
miss = X.isna().mean().round(3).to_dict()
meta = {'landmark': str(L.date()), 'feature_window_start': str(W0.date()), 'export_end': str(end.date()),
        'n_patients': int(len(X)), 'n_features': int(X.shape[1]), 'n_events_1y': int(y.sum()), 'n_deaths_1y': int(y_death.sum()), 'n_inpatient': int(alive.index.isin(acute).sum()),
        'prevalence': float(y.mean()), 'site_sizes': site.value_counts().sort_index().tolist(),
        'site_prevalence': y.groupby(site).mean().round(4).tolist(), 'missing_rate': miss,
        'features': list(X.columns)}
json.dump(meta, open(f'{out}_meta.json', 'w'), indent=1)
print(json.dumps({k: v for k, v in meta.items() if k not in ('missing_rate', 'features')}, indent=1))
