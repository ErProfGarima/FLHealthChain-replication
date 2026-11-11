package zk

import (
	"crypto/sha256"
	"fmt"
)

// Message is the byte string each hospital ring-signs for an update submission.
func Message(round uint64, ringID, commit string, proof []byte) []byte {
	ph := sha256.Sum256(proof)
	h := sha256.Sum256([]byte(fmt.Sprintf("FLHC|%d|%s|%s|%x", round, ringID, commit, ph)))
	return h[:]
}
