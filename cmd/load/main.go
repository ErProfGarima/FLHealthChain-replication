// load: closed-loop Fabric Gateway load generator. Each worker submits a transaction,
// waits for its commit status, records submit->commit latency, and moves to the next.
package main

import (
	"crypto/x509"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/hyperledger/fabric-gateway/pkg/client"
	"github.com/hyperledger/fabric-gateway/pkg/hash"
	"github.com/hyperledger/fabric-gateway/pkg/identity"
	"google.golang.org/grpc"
	"encoding/base64"
	"encoding/hex"
	"math/big"
	"strings"

	zk "flhc/zk"
	"flhc/zk/lsag"
	"google.golang.org/grpc/credentials"
)

const root = "/home/claude/flhc/net/crypto/peerOrganizations"

type Item struct {
	Round  uint64 `json:"round"`
	Ring   string `json:"ring"`
	Commit string `json:"commit"`
	Proof  string `json:"proof"`
	Sig    string `json:"sig"`
}

func gw(org int) (*client.Gateway, *grpc.ClientConn) {
	dom := fmt.Sprintf("hosp%d.flhc", org)
	tlsPEM, _ := os.ReadFile(filepath.Join(root, dom, "peers", "peer0."+dom, "tls/ca.crt"))
	cert, _ := identity.CertificateFromPEM(tlsPEM)
	pool := x509.NewCertPool(); pool.AddCert(cert)
	conn, err := grpc.NewClient(fmt.Sprintf("localhost:%d", 8050+10*org),
		grpc.WithTransportCredentials(credentials.NewClientTLSFromCert(pool, "localhost")))
	if err != nil { panic(err) }
	ud := filepath.Join(root, dom, "users", "User1@"+dom, "msp")
	cpem, _ := os.ReadFile(filepath.Join(ud, "signcerts", "User1@"+dom+"-cert.pem"))
	c, _ := identity.CertificateFromPEM(cpem)
	id, _ := identity.NewX509Identity(fmt.Sprintf("Hosp%dMSP", org), c)
	ks, _ := os.ReadDir(filepath.Join(ud, "keystore"))
	kpem, _ := os.ReadFile(filepath.Join(ud, "keystore", ks[0].Name()))
	pk, _ := identity.PrivateKeyFromPEM(kpem)
	sign, _ := identity.NewPrivateKeySign(pk)
	g, err := client.Connect(id, client.WithSign(sign), client.WithHash(hash.SHA256), client.WithClientConnection(conn),
		client.WithEvaluateTimeout(30*time.Second), client.WithEndorseTimeout(60*time.Second),
		client.WithSubmitTimeout(60*time.Second), client.WithCommitStatusTimeout(120*time.Second))
	if err != nil { panic(err) }
	return g, conn
}

func pct(x []float64, p float64) float64 {
	if len(x) == 0 { return 0 }
	i := int(p * float64(len(x)-1)); return x[i]
}

func main() {
	ch := flag.String("ch", "bft4", "channel")
	mode := flag.String("mode", "audit", "audit|update|setup")
	n := flag.Int("n", 2000, "transactions")
	conc := flag.Int("c", 50, "concurrent workers")
	items := flag.String("items", "", "items.json for update mode")
	tag := flag.String("tag", "", "run tag (unique ids)")
	out := flag.String("out", "", "json output")
	dir := flag.String("dir", "", "bench data dir (setup mode)")
	rings := flag.Int("rings", 5, "")
	flag.Parse()

	gws := make([]*client.Gateway, 4)
	for o := 1; o <= 4; o++ { g, conn := gw(o); defer conn.Close(); defer g.Close(); gws[o-1] = g }
	if *mode == "setup" {
		ct := gws[0].GetNetwork(*ch).GetContract("flhc")
		vk, _ := os.ReadFile(*dir + "/vk.b64")
		if _, err := ct.SubmitTransaction("SetVK", string(vk)); err != nil { panic(err) }
		for k := 0; k < *rings; k++ {
			csv, _ := os.ReadFile(fmt.Sprintf("%s/ring%d.csv", *dir, k))
			if _, err := ct.SubmitTransaction("InitRing", fmt.Sprintf("ring%d", k), string(csv)); err != nil { panic(err) }
		}
		fmt.Println("setup done"); return
	}
	if *mode == "attack" {
		var its []Item
		b, _ := os.ReadFile(*items); json.Unmarshal(b, &its)
		ct := gws[0].GetNetwork(*ch).GetContract("flhc")
		res := map[string][2]int{}
		try := func(class string, args []string, wantOK bool) {
			_, err := ct.SubmitTransaction("SubmitUpdate", args...)
			r := res[class]
			if (err == nil) == wantOK { r[0]++ } else { r[1]++; if r[1] <= 2 { fmt.Println(class, "unexpected:", err) } }
			res[class] = r
		}
		per := len(its) / 5
		for k := 0; k < per; k++ {
			it := its[k]
			c, _ := new(big.Int).SetString(it.Commit, 10)
			try("wrong_commitment", []string{fmt.Sprint(it.Round), it.Ring, new(big.Int).Add(c, big.NewInt(1)).String(), it.Proof, it.Sig}, false)
			try("proof_replay_other_round", []string{fmt.Sprint(it.Round + 1000), it.Ring, it.Commit, it.Proof, it.Sig}, false)
			sb, _ := base64.StdEncoding.DecodeString(it.Sig); sb[40] ^= 0x01
			try("tampered_signature", []string{fmt.Sprint(it.Round), it.Ring, it.Commit, it.Proof, base64.StdEncoding.EncodeToString(sb)}, false)
			// signer outside the ring: substitute member 0 with a fresh key, sign as that key
			csv, _ := os.ReadFile(fmt.Sprintf("%s/%s.csv", *dir, it.Ring))
			keys := strings.Split(string(csv), ",")
			ring := make([]lsag.Point, len(keys))
			for i, kx := range keys { bb, _ := hex.DecodeString(kx); ring[i], _ = lsag.ParsePoint(bb) }
			x, P := lsag.KeyGen(); ring[0] = P
			pb, _ := base64.StdEncoding.DecodeString(it.Proof)
			sig := lsag.Sign(zk.Message(it.Round, it.Ring, it.Commit, pb), ring, 0, x)
			try("outsider_signer", []string{fmt.Sprint(it.Round), it.Ring, it.Commit, it.Proof, base64.StdEncoding.EncodeToString(sig.Marshal())}, false)
			// duplicate: a valid submission is accepted once, then the same signer is rejected
			it2 := its[per+k]
			args := []string{fmt.Sprint(it2.Round), it2.Ring, it2.Commit, it2.Proof, it2.Sig}
			try("valid_first_submission", args, true)
			try("duplicate_key_image", args, false)
		}
		j, _ := json.MarshalIndent(res, "", " ")
		fmt.Println(string(j))
		if *out != "" { os.WriteFile(*out, j, 0644) }
		return
	}
	var its []Item
	if *mode == "update" {
		b, _ := os.ReadFile(*items); json.Unmarshal(b, &its)
		if *n > len(its) { *n = len(its) }
	}
	var next int64 = -1
	var mu sync.Mutex
	lat := []float64{}
	var ok, fail int64
	errs := map[string]int{}
	var wg sync.WaitGroup
	t0 := time.Now()
	for w := 0; w < *conc; w++ {
		wg.Add(1)
		go func(w int) {
			defer wg.Done()
			ct := gws[w%4].GetNetwork(*ch).GetContract("flhc")
			for {
				i := atomic.AddInt64(&next, 1)
				if i >= int64(*n) { return }
				var args []string; var fn string
				if *mode == "audit" {
					fn = "LogEvent"; args = []string{fmt.Sprintf("%s-%d", *tag, i), fmt.Sprintf("%064x", i)}
				} else {
					it := its[i]; fn = "SubmitUpdate"
					args = []string{fmt.Sprint(it.Round), it.Ring, it.Commit, it.Proof, it.Sig}
				}
				s := time.Now()
				_, commit, err := ct.SubmitAsync(fn, client.WithArguments(args...))
				if err == nil {
					var st *client.Status
					st, err = commit.Status()
					if err == nil && !st.Successful { err = fmt.Errorf("invalid: %v", st.Code) }
				}
				d := time.Since(s).Seconds() * 1000
				mu.Lock()
				if err != nil {
					fail++; m := err.Error(); if len(m) > 120 { m = m[:120] }; errs[m]++
				} else { ok++; lat = append(lat, d) }
				mu.Unlock()
			}
		}(w)
	}
	wg.Wait()
	el := time.Since(t0).Seconds()
	sort.Float64s(lat)
	mean := 0.0; for _, v := range lat { mean += v }; if len(lat) > 0 { mean /= float64(len(lat)) }
	res := map[string]any{"channel": *ch, "mode": *mode, "n": *n, "concurrency": *conc, "ok": ok, "fail": fail,
		"elapsed_s": el, "tps": float64(ok) / el, "lat_mean_ms": mean, "lat_p50_ms": pct(lat, .5),
		"lat_p95_ms": pct(lat, .95), "lat_p99_ms": pct(lat, .99), "errors": errs}
	j, _ := json.MarshalIndent(res, "", " ")
	fmt.Println(string(j))
	if *out != "" { os.WriteFile(*out, j, 0644) }
}
