#!/bin/bash
# usage: reset_net.sh N   (N orderers; creates channels bftN and raftN, deploys chaincode)
N=${1:-4}
cd /home/claude/flhc/net
pkill -f "bin/orderer"; pkill -f "peer node start"; pkill -f "flhc/zk/cc"; sleep 2
rm -rf data logs artifacts; mkdir -p logs artifacts
export PATH=/home/claude/flhc/dl/fabric/bin:$PATH
python3 gen_configtx.py $N
for p in BFT$N RAFT$N; do c=$(echo $p|tr A-Z a-z); FABRIC_CFG_PATH=$PWD configtxgen -profile $p -outputBlock artifacts/$c.block -channelID $c >/dev/null 2>&1 || echo "configtxgen failed $p"; done
./start_orderers.sh $N
R=crypto/ordererOrganizations/orderer.flhc
for c in bft$N raft$N; do for i in $(seq 0 $((N-1))); do D=$R/orderers/o$i.orderer.flhc
  osnadmin channel join --channelID $c --config-block artifacts/$c.block -o localhost:$((7051+10*i)) --ca-file $D/tls/ca.crt --client-cert $D/tls/server.crt --client-key $D/tls/server.key >/dev/null 2>&1 || echo "join fail $c o$i"; done; done
./start_peers.sh
sleep 3
for j in 1 2 3 4; do (source env.sh $j; for c in bft$N raft$N; do peer channel join -b artifacts/$c.block >/dev/null 2>&1 || echo "peer join fail $j $c"; done; peer lifecycle chaincode install flhc.tgz >/dev/null 2>&1); done
PKG=flhc_1:3eaf92128ad814f40b1f2315b4ce3fb9ea6e5e9b5df1a181b11ad8bc63b80517
(CHAINCODE_ID=$PKG CHAINCODE_SERVER_ADDRESS=127.0.0.1:9999 setsid nohup /home/claude/flhc/zk/cc > logs/cc.log 2>&1 &)
OC="-o localhost:7050 --tls --cafile $PWD/$R/orderers/o0.orderer.flhc/tls/ca.crt"
sleep 2
for c in bft$N raft$N; do for j in 1 2 3 4; do (source env.sh $j; peer lifecycle chaincode approveformyorg $OC -C $c -n flhc -v 1 --package-id $PKG --sequence 1 >/dev/null 2>&1 || echo "approve fail $c $j"); done; done
sleep 3
for c in bft$N raft$N; do (source env.sh 1; peer lifecycle chaincode commit $OC -C $c -n flhc -v 1 --sequence 1 $(cat peers.args) 2>&1 | grep -c "VALID"); done
