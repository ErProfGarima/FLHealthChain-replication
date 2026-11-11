// Package zk: FLHealthChain update-well-formedness circuit (Groth16, BN254).
// Statement: the prover knows a quantised update u in Z^N with |u_k| < 2^15 such that
//   (1) sum_k u_k^2 <= BoundSq            (L2 norm bound, i.e. ||u||_2 <= C after scaling)
//   (2) MiMC(RoundID || pack(u)) == Commit (the on-chain commitment binds exactly this u)
package zk

import (
	"github.com/consensys/gnark/frontend"
	"github.com/consensys/gnark/std/hash/mimc"
	"github.com/consensys/gnark/std/rangecheck"
)

const (
	Bits   = 16       // bits per quantised coordinate (offset-encoded)
	Offset = 1 << 15  // u = v - Offset
	Pack   = 15       // coordinates per field element (15*16 = 240 < 254)
)

type UpdateCircuit struct {
	Commit  frontend.Variable `gnark:",public"`
	BoundSq frontend.Variable `gnark:",public"`
	RoundID frontend.Variable `gnark:",public"`
	V       []frontend.Variable // offset-encoded coordinates, private
}

func (c *UpdateCircuit) Define(api frontend.API) error {
	rc := rangecheck.New(api)
	h, err := mimc.NewMiMC(api)
	if err != nil {
		return err
	}
	h.Write(c.RoundID)
	sum := frontend.Variable(0)
	acc := frontend.Variable(0)
	mul := frontend.Variable(1)
	cnt := 0
	for _, v := range c.V {
		rc.Check(v, Bits)
		u := api.Sub(v, Offset)
		sum = api.Add(sum, api.Mul(u, u))
		acc = api.Add(acc, api.Mul(v, mul))
		cnt++
		if cnt == Pack {
			h.Write(acc)
			acc, mul, cnt = 0, 1, 0
		} else {
			mul = api.Mul(mul, 1<<Bits)
		}
	}
	if cnt > 0 {
		h.Write(acc)
	}
	api.AssertIsLessOrEqual(sum, c.BoundSq)
	api.AssertIsEqual(h.Sum(), c.Commit)
	return nil
}
