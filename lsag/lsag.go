// Package lsag implements Linkable Spontaneous Anonymous Group signatures
// (Liu, Wei, Wong, ACISP 2004; Monero "MLSAG" single-key form) over secp256k1.
package lsag

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"errors"

	"github.com/decred/dcrd/dcrec/secp256k1/v4"
)

type Point = secp256k1.JacobianPoint
type Scalar = secp256k1.ModNScalar

type Signature struct {
	C0 Scalar
	S  []Scalar
	I  Point // key image
}

func randScalar() Scalar {
	var b [32]byte
	var s Scalar
	for {
		rand.Read(b[:])
		if overflow := s.SetBytes(&b); overflow == 0 && !s.IsZero() {
			return s
		}
	}
}

func enc(p *Point) []byte {
	q := *p
	q.ToAffine()
	return secp256k1.NewPublicKey(&q.X, &q.Y).SerializeCompressed()
}

// HashToPoint: try-and-increment onto secp256k1 (deterministic, no known discrete log).
func HashToPoint(p *Point) Point {
	base := enc(p)
	var ctr uint32
	for {
		h := sha256.New()
		h.Write([]byte("FLHC-LSAG-Hp"))
		h.Write(base)
		var c [4]byte
		binary.BigEndian.PutUint32(c[:], ctr)
		h.Write(c[:])
		d := h.Sum(nil)
		var x, y secp256k1.FieldVal
		if overflow := x.SetByteSlice(d); !overflow {
			if secp256k1.DecompressY(&x, false, &y) {
				var r Point
				r.X.Set(&x)
				r.Y.Set(&y)
				r.Z.SetInt(1)
				return r
			}
		}
		ctr++
	}
}

func hashScalar(prefix []byte, m []byte, L, R *Point) Scalar {
	h := sha256.New()
	h.Write(prefix)
	h.Write(m)
	h.Write(enc(L))
	h.Write(enc(R))
	var s Scalar
	var b [32]byte
	copy(b[:], h.Sum(nil))
	s.SetBytes(&b)
	return s
}

func ringPrefix(ring []Point) []byte {
	h := sha256.New()
	h.Write([]byte("FLHC-LSAG-ring"))
	for i := range ring {
		h.Write(enc(&ring[i]))
	}
	return h.Sum(nil)
}

func KeyGen() (Scalar, Point) {
	x := randScalar()
	var P Point
	secp256k1.ScalarBaseMultNonConst(&x, &P)
	P.ToAffine()
	return x, P
}

func lin(s *Scalar, A *Point, c *Scalar, B *Point) Point {
	// s*A + c*B
	var t1, t2, r Point
	secp256k1.ScalarMultNonConst(s, A, &t1)
	secp256k1.ScalarMultNonConst(c, B, &t2)
	secp256k1.AddNonConst(&t1, &t2, &r)
	return r
}

func gen() Point {
	var one Scalar
	one.SetInt(1)
	var G Point
	secp256k1.ScalarBaseMultNonConst(&one, &G)
	return G
}

func Sign(m []byte, ring []Point, pi int, x Scalar) Signature {
	n := len(ring)
	G := gen()
	pre := ringPrefix(ring)
	Hpi := HashToPoint(&ring[pi])
	var I Point
	secp256k1.ScalarMultNonConst(&x, &Hpi, &I)
	I.ToAffine()
	c := make([]Scalar, n)
	s := make([]Scalar, n)
	alpha := randScalar()
	var L, R Point
	secp256k1.ScalarBaseMultNonConst(&alpha, &L)
	secp256k1.ScalarMultNonConst(&alpha, &Hpi, &R)
	c[(pi+1)%n] = hashScalar(pre, m, &L, &R)
	for k := 1; k < n; k++ {
		i := (pi + k) % n
		s[i] = randScalar()
		L = lin(&s[i], &G, &c[i], &ring[i])
		Hi := HashToPoint(&ring[i])
		R = lin(&s[i], &Hi, &c[i], &I)
		c[(i+1)%n] = hashScalar(pre, m, &L, &R)
	}
	// s_pi = alpha - c_pi * x
	var cx Scalar
	cx.Mul2(&c[pi], &x)
	cx.Negate()
	s[pi].Add2(&alpha, &cx)
	return Signature{C0: c[0], S: s, I: I}
}

func Verify(m []byte, ring []Point, sig Signature) error {
	n := len(ring)
	if len(sig.S) != n {
		return errors.New("ring size mismatch")
	}
	G := gen()
	pre := ringPrefix(ring)
	c := sig.C0
	for i := 0; i < n; i++ {
		L := lin(&sig.S[i], &G, &c, &ring[i])
		Hi := HashToPoint(&ring[i])
		R := lin(&sig.S[i], &Hi, &c, &sig.I)
		c = hashScalar(pre, m, &L, &R)
	}
	if !c.Equals(&sig.C0) {
		return errors.New("invalid signature")
	}
	return nil
}

// Linked reports whether two signatures were produced with the same private key.
func Linked(a, b Signature) bool {
	return string(enc(&a.I)) == string(enc(&b.I))
}

// Size in bytes of the serialised signature: c0 || s_0..s_{n-1} || I(compressed)
func (s Signature) Size() int { return 32 + 32*len(s.S) + 33 }

// Marshal: c0 || s_0..s_{n-1} || I(compressed 33 bytes)
func (s Signature) Marshal() []byte {
	out := make([]byte, 0, s.Size())
	b := s.C0.Bytes()
	out = append(out, b[:]...)
	for i := range s.S {
		b = s.S[i].Bytes()
		out = append(out, b[:]...)
	}
	out = append(out, enc(&s.I)...)
	return out
}

func Unmarshal(b []byte, n int) (Signature, error) {
	var s Signature
	if len(b) != 32+32*n+33 {
		return s, errors.New("bad signature length")
	}
	var a [32]byte
	copy(a[:], b[:32])
	if s.C0.SetBytes(&a) != 0 {
		return s, errors.New("c0 overflow")
	}
	s.S = make([]Scalar, n)
	for i := 0; i < n; i++ {
		copy(a[:], b[32+32*i:64+32*i])
		if s.S[i].SetBytes(&a) != 0 {
			return s, errors.New("s overflow")
		}
	}
	pk, err := secp256k1.ParsePubKey(b[32+32*n:])
	if err != nil {
		return s, err
	}
	pk.AsJacobian(&s.I)
	return s, nil
}

func ParsePoint(b []byte) (Point, error) {
	var p Point
	pk, err := secp256k1.ParsePubKey(b)
	if err != nil {
		return p, err
	}
	pk.AsJacobian(&p)
	return p, nil
}

func Encode(p Point) []byte { return enc(&p) }

func KeyImageHex(s Signature) string {
	const hx = "0123456789abcdef"
	e := enc(&s.I)
	out := make([]byte, 2*len(e))
	for i, c := range e {
		out[2*i], out[2*i+1] = hx[c>>4], hx[c&15]
	}
	return string(out)
}
