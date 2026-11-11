package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"time"

	"flhc/zk/lsag"
)

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1000 }
func stats(x []float64) (float64, float64) {
	m := 0.0
	for _, v := range x { m += v }
	m /= float64(len(x))
	s := 0.0
	for _, v := range x { s += (v - m) * (v - m) }
	return m, math.Sqrt(s / float64(len(x)-1))
}

func main() {
	out := []map[string]any{}
	for _, n := range []int{5, 10, 15, 20, 25, 30} {
		xs := make([]lsag.Scalar, n)
		ring := make([]lsag.Point, n)
		for i := range ring { xs[i], ring[i] = lsag.KeyGen() }
		var st, vt []float64
		var size int
		okAll, tamperRejected, linkOK, unlinkOK := true, true, true, true
		for r := 0; r < 30; r++ {
			pi := r % n
			msg := []byte(fmt.Sprintf("update-commitment-round-%d", r))
			t := time.Now()
			sig := lsag.Sign(msg, ring, pi, xs[pi])
			st = append(st, ms(time.Since(t)))
			t = time.Now()
			if lsag.Verify(msg, ring, sig) != nil { okAll = false }
			vt = append(vt, ms(time.Since(t)))
			size = sig.Size()
			if lsag.Verify(append(msg, 'x'), ring, sig) == nil { tamperRejected = false }
			sig2 := lsag.Sign([]byte("other"), ring, pi, xs[pi])
			if !lsag.Linked(sig, sig2) { linkOK = false }
			sig3 := lsag.Sign(msg, ring, (pi+1)%n, xs[(pi+1)%n])
			if lsag.Linked(sig, sig3) { unlinkOK = false }
		}
		sm, ss := stats(st)
		vm, vs := stats(vt)
		row := map[string]any{"ring": n, "sign_ms": sm, "sign_sd": ss, "verify_ms": vm, "verify_sd": vs,
			"sig_bytes": size, "all_valid": okAll, "tamper_rejected": tamperRejected,
			"same_key_linked": linkOK, "diff_key_unlinked": unlinkOK, "reps": 30}
		out = append(out, row)
		fmt.Println(row)
	}
	j, _ := json.MarshalIndent(out, "", "  ")
	os.WriteFile("lsag_bench.json", j, 0644)
}
