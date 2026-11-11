#!/bin/bash
cd /home/claude/flhc/zk
./bench -n 3090 -reps 10 -out results/zk_model.json > results/zk_model.log 2>&1
./lsagbench > results/lsag.log 2>&1 && cp lsag_bench.json results/lsag_bench.json
./bench -n 1000 -reps 3 -out results/zk_scale_1000.json > /dev/null 2>&1
./bench -n 7000 -reps 3 -out results/zk_scale_7000.json > /dev/null 2>&1
./bench -n 14530 -reps 3 -out results/zk_14530.json > /dev/null 2>&1
echo DONE > results/zk_done
