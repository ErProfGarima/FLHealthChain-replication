import os, sys
NORD=int(sys.argv[1]) if len(sys.argv)>1 else 4
R=os.path.abspath('crypto')
def opath(i,*p): return os.path.join(R,'ordererOrganizations/orderer.flhc/orderers',f'o{i}.orderer.flhc',*p)
def oport(i): return 7050+10*i
orgs=[f'Hosp{j}' for j in range(1,5)]
L=[]
w=L.append
w('Organizations:')
w('  - &OrdererOrg')
w('    Name: OrdererMSP'); w('    ID: OrdererMSP')
w(f'    MSPDir: {R}/ordererOrganizations/orderer.flhc/msp')
w('    Policies:')
for p,r in [('Readers',"OR('OrdererMSP.member')"),('Writers',"OR('OrdererMSP.member')"),('Admins',"OR('OrdererMSP.admin')")]:
    w(f'      {p}:'); w('        Type: Signature'); w(f'        Rule: "{r}"')
w('    OrdererEndpoints:')
for i in range(NORD): w(f'      - localhost:{oport(i)}')
for j,o in enumerate(orgs,1):
    m=f'{o}MSP'
    w(f'  - &{o}'); w(f'    Name: {m}'); w(f'    ID: {m}')
    w(f'    MSPDir: {R}/peerOrganizations/hosp{j}.flhc/msp')
    w('    Policies:')
    for p,r in [('Readers',f"OR('{m}.admin','{m}.peer','{m}.client')"),('Writers',f"OR('{m}.admin','{m}.client')"),('Admins',f"OR('{m}.admin')"),('Endorsement',f"OR('{m}.peer')")]:
        w(f'      {p}:'); w('        Type: Signature'); w(f'        Rule: "{r}"')
    w('    AnchorPeers:'); w(f'      - Host: localhost'); w(f'        Port: {8050+10*j}')
w('''Capabilities:
  Channel: &ChannelCapabilities
    V3_0: true
  Orderer: &OrdererCapabilities
    V2_0: true
  Application: &ApplicationCapabilities
    V2_5: true
Application: &ApplicationDefaults
  Organizations:
  Policies:
    Readers: {Type: ImplicitMeta, Rule: "ANY Readers"}
    Writers: {Type: ImplicitMeta, Rule: "ANY Writers"}
    Admins: {Type: ImplicitMeta, Rule: "MAJORITY Admins"}
    LifecycleEndorsement: {Type: ImplicitMeta, Rule: "MAJORITY Endorsement"}
    Endorsement: {Type: ImplicitMeta, Rule: "MAJORITY Endorsement"}
  Capabilities:
    <<: *ApplicationCapabilities
Channel: &ChannelDefaults
  Policies:
    Readers: {Type: ImplicitMeta, Rule: "ANY Readers"}
    Writers: {Type: ImplicitMeta, Rule: "ANY Writers"}
    Admins: {Type: ImplicitMeta, Rule: "MAJORITY Admins"}
  Capabilities:
    <<: *ChannelCapabilities
Profiles:''')
def orderer_common():
    return ['      Organizations:','        - *OrdererOrg',
    '      Policies:',
    '        Readers: {Type: ImplicitMeta, Rule: "ANY Readers"}',
    '        Writers: {Type: ImplicitMeta, Rule: "ANY Writers"}',
    '        Admins: {Type: ImplicitMeta, Rule: "MAJORITY Admins"}',
    '        BlockValidation: {Type: ImplicitMeta, Rule: "ANY Writers"}',
    '      BatchTimeout: 500ms',
    '      BatchSize: {MaxMessageCount: 500, AbsoluteMaxBytes: 10 MB, PreferredMaxBytes: 2 MB}',
    '      Capabilities:','        <<: *OrdererCapabilities']
def app():
    return ['    Application:','      <<: *ApplicationDefaults','      Organizations:']+[f'        - *{o}' for o in orgs]
for n in (NORD,):
    w(f'  BFT{n}:'); w('    <<: *ChannelDefaults'); w('    Orderer:'); w('      OrdererType: BFT')
    L.extend(orderer_common())
    w('      SmartBFT:')
    for k,v in [('RequestBatchMaxInterval','50ms'),('RequestForwardTimeout','2s'),('RequestComplainTimeout','20s'),('RequestAutoRemoveTimeout','3m0s'),('ViewChangeResendInterval','5s'),('ViewChangeTimeout','20s'),('LeaderHeartbeatTimeout','1m0s'),('CollectTimeout','1s'),('IncomingMessageBufferSize',200),('RequestPoolSize',100000),('LeaderHeartbeatCount',10),('RequestBatchMaxCount',500),('RequestBatchMaxBytes',2097152)]:
        w(f'        {k}: {v}')
    w('      ConsenterMapping:')
    for i in range(n):
        w(f'        - ID: {i+1}'); w('          Host: localhost'); w(f'          Port: {oport(i)}'); w('          MSPID: OrdererMSP')
        w(f'          Identity: {opath(i,"msp/signcerts",f"o{i}.orderer.flhc-cert.pem")}')
        w(f'          ClientTLSCert: {opath(i,"tls/server.crt")}'); w(f'          ServerTLSCert: {opath(i,"tls/server.crt")}')
    L.extend(app())
    w(f'  RAFT{n}:'); w('    <<: *ChannelDefaults'); w('    Orderer:'); w('      OrdererType: etcdraft')
    L.extend(orderer_common())
    w('      EtcdRaft:'); w('        Consenters:')
    for i in range(n):
        w('          - Host: localhost'); w(f'            Port: {oport(i)}')
        w(f'            ClientTLSCert: {opath(i,"tls/server.crt")}'); w(f'            ServerTLSCert: {opath(i,"tls/server.crt")}')
        if False: pass
    w('        Options: {TickInterval: 500ms, ElectionTick: 10, HeartbeatTick: 1, MaxInflightBlocks: 5, SnapshotIntervalSize: 16 MB}')
    L.extend(app())
open('configtx.yaml','w').write('\n'.join(L)+'\n')
