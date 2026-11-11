// FLHealthChain chaincode (chaincode-as-a-service).
// MVC: SubmitUpdate verifies a Groth16 update-well-formedness proof and an LSAG ring signature
//      on the endorsing peer, enforces one update per (ring, round, key image), and stores
//      ~1 KB of evidence on-chain (commitment, proof, key image). The model update itself is off-chain.
// CMC: GrantConsent / RevokeConsent.  ATC: LogEvent (append-only audit record).
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
	"os"
	"strconv"
	"strings"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/hyperledger/fabric-chaincode-go/v2/shim"
	"github.com/hyperledger/fabric-contract-api-go/v2/contractapi"

	zk "flhc/zk"
	"flhc/zk/lsag"
)

const BoundSq = 4096 * 4096

type Contract struct{ contractapi.Contract }

type UpdateRecord struct {
	Round     uint64 `json:"round"`
	Ring      string `json:"ring"`
	Commit    string `json:"commit"`
	KeyImage  string `json:"keyImage"`
	Proof     string `json:"proof"`
	ProofHash string `json:"proofHash"`
	TxID      string `json:"txId"`
}

func (c *Contract) SetVK(ctx contractapi.TransactionContextInterface, vkB64 string) error {
	b, err := base64.StdEncoding.DecodeString(vkB64)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState("vk", b)
}

func (c *Contract) InitRing(ctx contractapi.TransactionContextInterface, ringID string, keysHexCSV string) error {
	keys := strings.Split(keysHexCSV, ",")
	for _, k := range keys {
		b, err := hex.DecodeString(k)
		if err != nil {
			return err
		}
		if _, err := lsag.ParsePoint(b); err != nil {
			return fmt.Errorf("bad key: %v", err)
		}
	}
	return ctx.GetStub().PutState("ring~"+ringID, []byte(keysHexCSV))
}

func (c *Contract) SubmitUpdate(ctx contractapi.TransactionContextInterface, roundS, ringID, commitDec, proofB64, sigB64 string) error {
	stub := ctx.GetStub()
	round, err := strconv.ParseUint(roundS, 10, 64)
	if err != nil {
		return err
	}
	vkb, err := stub.GetState("vk")
	if err != nil || vkb == nil {
		return fmt.Errorf("verifying key not set")
	}
	vk := groth16.NewVerifyingKey(ecc.BN254)
	if _, err := vk.ReadFrom(bytes.NewReader(vkb)); err != nil {
		return err
	}
	proofB, err := base64.StdEncoding.DecodeString(proofB64)
	if err != nil {
		return err
	}
	proof := groth16.NewProof(ecc.BN254)
	if _, err := proof.ReadFrom(bytes.NewReader(proofB)); err != nil {
		return fmt.Errorf("bad proof encoding: %v", err)
	}
	com, ok := new(big.Int).SetString(commitDec, 10)
	if !ok {
		return fmt.Errorf("bad commitment")
	}
	pubAssign := &zk.UpdateCircuit{Commit: com, BoundSq: BoundSq, RoundID: round}
	pub, err := frontend.NewWitness(pubAssign, ecc.BN254.ScalarField(), frontend.PublicOnly())
	if err != nil {
		return err
	}
	if err := groth16.Verify(proof, vk, pub); err != nil {
		return fmt.Errorf("zk-SNARK verification failed: %v", err)
	}
	ringCSV, err := stub.GetState("ring~" + ringID)
	if err != nil || ringCSV == nil {
		return fmt.Errorf("unknown ring")
	}
	keys := strings.Split(string(ringCSV), ",")
	ring := make([]lsag.Point, len(keys))
	for i, k := range keys {
		b, _ := hex.DecodeString(k)
		ring[i], _ = lsag.ParsePoint(b)
	}
	sigB, err := base64.StdEncoding.DecodeString(sigB64)
	if err != nil {
		return err
	}
	sig, err := lsag.Unmarshal(sigB, len(ring))
	if err != nil {
		return err
	}
	if err := lsag.Verify(zk.Message(round, ringID, commitDec, proofB), ring, sig); err != nil {
		return fmt.Errorf("ring signature verification failed: %v", err)
	}
	ki := lsag.KeyImageHex(sig)
	key, _ := stub.CreateCompositeKey("upd", []string{ringID, roundS, ki})
	prev, err := stub.GetState(key)
	if err != nil {
		return err
	}
	if prev != nil {
		return fmt.Errorf("duplicate submission: key image already used in this round")
	}
	ph := sha256.Sum256(proofB)
	rec := UpdateRecord{Round: round, Ring: ringID, Commit: commitDec, KeyImage: ki,
		Proof: proofB64, ProofHash: hex.EncodeToString(ph[:]), TxID: stub.GetTxID()}
	j, _ := json.Marshal(rec)
	if err := stub.PutState(key, j); err != nil {
		return err
	}
	return stub.SetEvent("UpdateAccepted", j)
}

func (c *Contract) GrantConsent(ctx contractapi.TransactionContextInterface, pseudoID, scope string) error {
	k, _ := ctx.GetStub().CreateCompositeKey("consent", []string{pseudoID, scope})
	return ctx.GetStub().PutState(k, []byte("granted|"+ctx.GetStub().GetTxID()))
}

func (c *Contract) RevokeConsent(ctx contractapi.TransactionContextInterface, pseudoID, scope string) error {
	k, _ := ctx.GetStub().CreateCompositeKey("consent", []string{pseudoID, scope})
	if err := ctx.GetStub().PutState(k, []byte("revoked|"+ctx.GetStub().GetTxID())); err != nil {
		return err
	}
	return ctx.GetStub().SetEvent("ConsentRevoked", []byte(pseudoID+"|"+scope))
}

func (c *Contract) LogEvent(ctx contractapi.TransactionContextInterface, id, digest string) error {
	k, _ := ctx.GetStub().CreateCompositeKey("audit", []string{id})
	return ctx.GetStub().PutState(k, []byte(digest))
}

func (c *Contract) Get(ctx contractapi.TransactionContextInterface, key string) (string, error) {
	b, err := ctx.GetStub().GetState(key)
	return string(b), err
}

func main() {
	cc, err := contractapi.NewChaincode(&Contract{})
	if err != nil {
		panic(err)
	}
	server := &shim.ChaincodeServer{
		CCID:    os.Getenv("CHAINCODE_ID"),
		Address: os.Getenv("CHAINCODE_SERVER_ADDRESS"),
		CC:      cc,
		TLSProps: shim.TLSProperties{Disabled: true},
	}
	if err := server.Start(); err != nil {
		panic(err)
	}
}
