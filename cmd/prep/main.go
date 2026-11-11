// prep: one-time Groth16 setup (saved), R real update proofs, K rings of M hospital keys,
// and R*K*M fully signed SubmitUpdate payloads for the ledger benchmark.
package main

import (
	"bytes"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"math/rand"
	"os"
	"strings"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"

	zk "flhc/zk"
	"flhc/zk/lsag"
)

type Item struct {
	Round  uint64 `json:"round"`
	Ring   string `json:"ring"`
	Commit string `json:"commit"`
	Proof  string `json:"proof"`
	Sig    string `json:"sig"`
}

func main() {
	R := flag.Int("rounds", 20, "")
	K := flag.Int("rings", 5, "")
	M := flag.Int("members", 20, "")
	n := flag.Int("n", 14530, "")
	dir := flag.String("dir", "bench_data", "")
	flag.Parse()
	os.MkdirAll(*dir, 0755)
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, &zk.UpdateCircuit{V: make([]frontend.Variable, *n)})
	if err != nil { panic(err) }
	var pk groth16.ProvingKey
	var vk groth16.VerifyingKey
	if f, err := os.Open(*dir + "/pk.bin"); err == nil {
		pk = groth16.NewProvingKey(ecc.BN254); pk.ReadFrom(f); f.Close()
		vk = groth16.NewVerifyingKey(ecc.BN254)
		g, _ := os.Open(*dir + "/vk.bin"); vk.ReadFrom(g); g.Close()
	} else {
		pk, vk, err = groth16.Setup(ccs)
		if err != nil { panic(err) }
		f, _ := os.Create(*dir + "/pk.bin"); pk.WriteTo(f); f.Close()
		g, _ := os.Create(*dir + "/vk.bin"); vk.WriteTo(g); g.Close()
	}
	var vkb bytes.Buffer; vk.WriteTo(&vkb)
	os.WriteFile(*dir+"/vk.b64", []byte(base64.StdEncoding.EncodeToString(vkb.Bytes())), 0644)
	// rings
	type ringT struct{ xs []lsag.Scalar; ps []lsag.Point; csv string }
	rings := make([]ringT, *K)
	for k := range rings {
		var hx []string
		for i := 0; i < *M; i++ {
			x, p := lsag.KeyGen()
			rings[k].xs = append(rings[k].xs, x); rings[k].ps = append(rings[k].ps, p)
			hx = append(hx, hex.EncodeToString(lsag.Encode(p)))
		}
		rings[k].csv = strings.Join(hx, ",")
		os.WriteFile(fmt.Sprintf("%s/ring%d.csv", *dir, k), []byte(rings[k].csv), 0644)
	}
	rng := rand.New(rand.NewSource(11))
	var items []Item
	var proveTimes []float64
	for r := 1; r <= *R; r++ {
		f := make([]float64, *n); nrm := 0.0
		for i := range f { f[i] = rng.NormFloat64(); nrm += f[i] * f[i] }
		nrm = math.Sqrt(nrm)
		v := make([]uint32, *n); vv := make([]frontend.Variable, *n)
		for i := range f { q := int64(math.Trunc(f[i] / nrm * 0.999 * 4096)); v[i] = uint32(q + zk.Offset); vv[i] = v[i] }
		com := zk.Commit(uint64(r), v)
		wit, _ := frontend.NewWitness(&zk.UpdateCircuit{Commit: com, BoundSq: 4096 * 4096, RoundID: uint64(r), V: vv}, ecc.BN254.ScalarField())
		t := time.Now()
		proof, err := groth16.Prove(ccs, pk, wit)
		if err != nil { panic(err) }
		proveTimes = append(proveTimes, time.Since(t).Seconds())
		var pb bytes.Buffer; proof.WriteTo(&pb)
		p64 := base64.StdEncoding.EncodeToString(pb.Bytes())
		for k := range rings {
			rid := fmt.Sprintf("ring%d", k)
			for i := 0; i < *M; i++ {
				msg := zk.Message(uint64(r), rid, com.String(), pb.Bytes())
				sig := lsag.Sign(msg, rings[k].ps, i, rings[k].xs[i])
				items = append(items, Item{uint64(r), rid, com.String(), p64, base64.StdEncoding.EncodeToString(sig.Marshal())})
			}
		}
		fmt.Printf("round %d proved in %.2fs\n", r, proveTimes[len(proveTimes)-1])
	}
	j, _ := json.Marshal(items)
	os.WriteFile(*dir+"/items.json", j, 0644)
	pt, _ := json.Marshal(proveTimes)
	os.WriteFile(*dir+"/prove_times.json", pt, 0644)
	fmt.Println("items:", len(items))
}
