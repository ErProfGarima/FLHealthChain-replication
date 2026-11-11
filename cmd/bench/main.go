package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"math/rand"
	"os"
	"runtime"
	"sort"
	"time"

	"github.com/consensys/gnark-crypto/ecc"
	"github.com/consensys/gnark/backend/groth16"
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/frontend/cs/r1cs"

	zk "flhc/zk"
)

func median(x []float64) float64 { s := append([]float64{}, x...); sort.Float64s(s); return s[len(s)/2] }
func mean(x []float64) float64   { t := 0.0; for _, v := range x { t += v }; return t / float64(len(x)) }
func sd(x []float64) float64 {
	m := mean(x); t := 0.0
	for _, v := range x { t += (v - m) * (v - m) }
	return math.Sqrt(t / float64(len(x)-1))
}

func main() {
	n := flag.Int("n", 14530, "number of model parameters")
	reps := flag.Int("reps", 5, "proving repetitions")
	out := flag.String("out", "zk_bench.json", "output")
	flag.Parse()
	scale := 4096.0 // 2^12 fixed point, C = 1.0
	boundSq := int64(scale * scale)

	circ := &zk.UpdateCircuit{V: make([]frontend.Variable, *n)}
	t0 := time.Now()
	ccs, err := frontend.Compile(ecc.BN254.ScalarField(), r1cs.NewBuilder, circ)
	if err != nil { panic(err) }
	compile := time.Since(t0).Seconds()
	t0 = time.Now()
	pk, vk, err := groth16.Setup(ccs)
	if err != nil { panic(err) }
	setup := time.Since(t0).Seconds()

	rng := rand.New(rand.NewSource(7))
	var proveT, verifyT []float64
	var proofBytes, proofBytesUncompressed int
	rejectedOverNorm := false
	for r := 0; r < *reps; r++ {
		// random update, clipped to L2 norm 1.0 then quantised
		f := make([]float64, *n); nrm := 0.0
		for i := range f { f[i] = rng.NormFloat64(); nrm += f[i] * f[i] }
		nrm = math.Sqrt(nrm)
		v := make([]uint32, *n); vv := make([]frontend.Variable, *n)
		for i := range f {
			q := int64(math.Trunc(f[i] / nrm * 0.999 * scale))
			v[i] = uint32(q + zk.Offset); vv[i] = v[i]
		}
		round := uint64(r + 1)
		com := zk.Commit(round, v)
		w := &zk.UpdateCircuit{Commit: com, BoundSq: boundSq, RoundID: round, V: vv}
		wit, err := frontend.NewWitness(w, ecc.BN254.ScalarField())
		if err != nil { panic(err) }
		pub, _ := wit.Public()
		t0 = time.Now()
		proof, err := groth16.Prove(ccs, pk, wit)
		if err != nil { panic(err) }
		proveT = append(proveT, time.Since(t0).Seconds())
		t0 = time.Now()
		if err := groth16.Verify(proof, vk, pub); err != nil { panic(err) }
		verifyT = append(verifyT, time.Since(t0).Seconds()*1000)
		var b bytes.Buffer
		proof.WriteTo(&b); proofBytes = b.Len()
		b.Reset(); proof.WriteRawTo(&b); proofBytesUncompressed = b.Len()
		if r == 0 {
			// negative test: scale update by 2 (norm 2C) -> prover must fail
			bad := make([]frontend.Variable, *n); bv := make([]uint32, *n)
			for i := range v { q := (int64(v[i]) - zk.Offset) * 2; bv[i] = uint32(q + zk.Offset); bad[i] = bv[i] }
			bw := &zk.UpdateCircuit{Commit: zk.Commit(round, bv), BoundSq: boundSq, RoundID: round, V: bad}
			bwit, _ := frontend.NewWitness(bw, ecc.BN254.ScalarField())
			_, err := groth16.Prove(ccs, pk, bwit)
			rejectedOverNorm = err != nil
		}
	}
	var vkb bytes.Buffer; vk.WriteTo(&vkb)
	// native commitment recomputation cost (aggregator side), 20 repetitions
	cv := make([]uint32, *n)
	for i := range cv { cv[i] = uint32(rng.Intn(1 << 16)) }
	t0 = time.Now()
	for k := 0; k < 20; k++ { zk.Commit(uint64(k), cv) }
	commitMs := time.Since(t0).Seconds() * 1000 / 20
	res := map[string]any{
		"n_params": *n, "constraints": ccs.GetNbConstraints(), "public_inputs": 3,
		"compile_s": compile, "setup_s": setup,
		"prove_s_mean": mean(proveT), "prove_s_sd": sd(proveT), "prove_s_median": median(proveT), "prove_s_all": proveT,
		"verify_ms_mean": mean(verifyT), "verify_ms_sd": sd(verifyT),
		"proof_bytes_compressed": proofBytes, "proof_bytes_uncompressed": proofBytesUncompressed,
		"vk_bytes": vkb.Len(), "cpus": runtime.NumCPU(), "reps": *reps,
		"over_norm_update_rejected": rejectedOverNorm, "commit_ms": commitMs,
	}
	j, _ := json.MarshalIndent(res, "", "  ")
	os.WriteFile(*out, j, 0644)
	fmt.Println(string(j))
}
