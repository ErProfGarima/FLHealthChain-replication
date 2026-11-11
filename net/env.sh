# source env.sh <org 1-4>
export PATH=/home/claude/flhc/dl/fabric/bin:$PATH
export FABRIC_CFG_PATH=/home/claude/flhc/net/peercfg
j=$1
export CORE_PEER_LOCALMSPID=Hosp${j}MSP
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_TLS_ROOTCERT_FILE=/home/claude/flhc/net/crypto/peerOrganizations/hosp$j.flhc/peers/peer0.hosp$j.flhc/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=/home/claude/flhc/net/crypto/peerOrganizations/hosp$j.flhc/users/Admin@hosp$j.flhc/msp
export CORE_PEER_ADDRESS=localhost:$((8050+10*j))
export ORDERER_CA=/home/claude/flhc/net/crypto/ordererOrganizations/orderer.flhc/orderers/o0.orderer.flhc/tls/ca.crt
