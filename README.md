# FLHealthChain — replication package (revision of IET Blockchain BLC-2026-06-0154)

Every number reported in the revised manuscript can be regenerated from the files in this package.

## 1. Synthetic cohort (fl/)
- Generate the data with Synthea (`synthea-with-dependencies.jar`, master-branch-latest). Use three runs with seeds 2026, 2027 and 2028:
  `java -jar synthea-with-dependencies.jar -s <seed> -p <N> -a 45-90 --exporter.csv.export=true --exporter.fhir.export=false --exporter.years_of_history=3 Massachusetts`
  The runs used N = 12000, 8000 and 6000. All three were stopped early by memory and time limits, so the cohort contains fewer patients than requested.
- Merge the runs: `python merge_batches.py merged run1/csv:trunc run2/csv:trunc run3/csv:trunc` (this drops the last 5 patients of each interrupted run).
- Build the cohort: `python build_dataset.py merged final/c 20`. The cohort used in the paper is in `fl/cohort/` (features, labels, sites, coordinates and metadata).
- Run the experiments: `python run_experiments.py final/c <part> <nparts>`. Results (one JSON per run) are in `fl/results/fl/`.
- Validation tuning results are in `tune_val_final.json` and `tune_cs_*.json`.

## 2. Cryptography (zk/)
- The Go module uses gnark v0.13.0 and decred secp256k1 v4.4.0. In our offline build, the `replace` lines in `go.mod` point to local clones of the golang.org/x, google.golang.org and gopkg.in modules. Remove them if you have normal Go proxy access.
- Groth16 benchmark: `go build ./cmd/bench && ./bench -n 3090 -reps 10`.
- LSAG benchmark: `go build ./cmd/lsagbench && ./lsagbench`.
- Results are in `zk/results/`.

## 3. Fabric network and ledger benchmark (net/, ledger_scripts/, zk/cmd/cc, zk/cmd/load)
- Uses the Hyperledger Fabric 3.1.1 native binaries (hyperledger-fabric-linux-amd64-3.1.1.tar.gz), with the chaincode deployed as an external service (`zk/cmd/cc`).
- `net/reset_net.sh 4` generates crypto material (cryptogen) and the channel blocks for the BFT and Raft profiles, starts 4 orderers and 4 peers, and deploys the chaincode.
- `zk/cmd/prep` pre-generates proofs and ring signatures. `ledger_scripts/run_ledger_bench.sh 4` runs the anchor, update and attack workloads (`./run_ledger_bench.sh 7` runs the seven-orderer variant).
- Raw results are in `zk/results/ledger/`. `envelope.json` holds the transaction sizes measured from committed blocks.

## 4. Tables and figures (paper/)
- `python compute_results.py` regenerates `values.json`, `tables.json` and Figures 3–6. `python arch_figs.py` regenerates Figures 1, 2 and 7.

Hardware used: a single cloud VM with 2 vCPU and 8 GB RAM.
