#!/bin/bash
# usage: run_ledger_bench.sh N  (expects network reset with N orderers)
N=${1:-4}
cd /home/claude/flhc/zk; R=results/ledger; mkdir -p $R
log(){ echo "$(date +%T) $*" >> $R/progress_n$N.log; }
./load -mode setup -ch bft$N -dir bench_data -rings 5 >> $R/progress_n$N.log 2>&1
./load -mode setup -ch raft$N -dir bench_data -rings 5 >> $R/progress_n$N.log 2>&1
sleep 20
./load -mode audit -ch bft$N -n 400 -c 20 -tag warm$N > /dev/null 2>&1
./load -mode audit -ch raft$N -n 400 -c 20 -tag warm$N > /dev/null 2>&1
python3 - <<'P'
import json
items=json.load(open('bench_data/items.json'))
for k in range(4): json.dump(items[k*450:(k+1)*450],open(f'bench_data/items_part{k}.json','w'))
json.dump(items[1800:2000],open('bench_data/items_attack.json','w'))
P
if [ "$N" = "4" ]; then CS="10 50 100 200"; REPS="1 2 3"; PARTS="0 1 2 3"; else CS="100"; REPS="1 2 3"; PARTS="0 1"; fi
for rep in $REPS; do for c in $CS; do for ch in bft$N raft$N; do
  f=$R/audit_${ch}_c${c}_r${rep}.json
  [ -f $f ] || ./load -mode audit -ch $ch -n 2000 -c $c -tag n${N}a${rep}c${c} -out $f > /dev/null 2>&1
  log "audit $ch c=$c r=$rep done"
done; done; done
for k in $PARTS; do for ch in bft$N raft$N; do
  f=$R/update_${ch}_part$k.json
  [ -f $f ] || ./load -mode update -ch $ch -items bench_data/items_part$k.json -n 450 -c 50 -out $f > /dev/null 2>&1
  log "update $ch part$k done"
done; done
if [ "$N" = "4" ]; then ./load -mode attack -ch bft4 -items bench_data/items_attack.json -dir bench_data -out $R/attack_bft4.json >> $R/progress_n$N.log 2>&1; log "attack done"; fi
log "ALL DONE"
