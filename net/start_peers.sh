#!/bin/bash
B=/home/claude/flhc/dl/fabric
for j in 1 2 3 4; do
  P=$((8050+10*j)); C=$((P+1)); O=$((P+2))
  D=/home/claude/flhc/net/crypto/peerOrganizations/hosp$j.flhc/peers/peer0.hosp$j.flhc
  env FABRIC_CFG_PATH=/home/claude/flhc/net/peercfg CORE_PEER_ID=peer0.hosp$j \
  CORE_PEER_ADDRESS=localhost:$P CORE_PEER_LISTENADDRESS=127.0.0.1:$P \
  CORE_PEER_CHAINCODEADDRESS=localhost:$C CORE_PEER_CHAINCODELISTENADDRESS=127.0.0.1:$C \
  CORE_PEER_GOSSIP_BOOTSTRAP=localhost:$P CORE_PEER_GOSSIP_EXTERNALENDPOINT=localhost:$P \
  CORE_PEER_LOCALMSPID=Hosp${j}MSP CORE_PEER_MSPCONFIGPATH=$D/msp \
  CORE_PEER_TLS_ENABLED=true CORE_PEER_TLS_CERT_FILE=$D/tls/server.crt CORE_PEER_TLS_KEY_FILE=$D/tls/server.key \
  CORE_PEER_TLS_ROOTCERT_FILE=$D/tls/ca.crt CORE_PEER_FILESYSTEMPATH=/home/claude/flhc/net/data/peer$j \
  CORE_OPERATIONS_LISTENADDRESS=127.0.0.1:$O CORE_METRICS_PROVIDER=prometheus FABRIC_LOGGING_SPEC=warn \
  CORE_PEER_GOSSIP_USELEADERELECTION=false CORE_PEER_GOSSIP_ORGLEADER=true \
  setsid nohup $B/bin/peer node start > logs/peer$j.log 2>&1 &
done
sleep 4
