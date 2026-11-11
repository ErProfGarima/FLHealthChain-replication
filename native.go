package zk

import (
	"math/big"

	"github.com/consensys/gnark-crypto/ecc/bn254/fr"
	"github.com/consensys/gnark-crypto/ecc/bn254/fr/mimc"
)

// Commit computes MiMC(RoundID || pack(v)) natively, matching the circuit.
func Commit(round uint64, v []uint32) *big.Int {
	h := mimc.NewMiMC()
	var e fr.Element
	e.SetUint64(round)
	b := e.Bytes()
	h.Write(b[:])
	acc := new(big.Int)
	mul := big.NewInt(1)
	cnt := 0
	shift := new(big.Int).Lsh(big.NewInt(1), Bits)
	flush := func() {
		var x fr.Element
		x.SetBigInt(acc)
		bb := x.Bytes()
		h.Write(bb[:])
		acc = new(big.Int)
		mul = big.NewInt(1)
		cnt = 0
	}
	for _, x := range v {
		acc.Add(acc, new(big.Int).Mul(big.NewInt(int64(x)), mul))
		cnt++
		if cnt == Pack {
			flush()
		} else {
			mul = new(big.Int).Mul(mul, shift)
		}
	}
	if cnt > 0 {
		flush()
	}
	out := h.Sum(nil)
	return new(big.Int).SetBytes(out)
}
