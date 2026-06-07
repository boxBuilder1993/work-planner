//go:build integration

package integration

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"testing"
	"time"
)

// baseURL / internalKey come from env so the same tests run against the
// local test stack (make test-e2e) and CI. Defaults match
// docker-compose.test.yml.
func baseURL() string {
	if v := os.Getenv("TEST_BASE_URL"); v != "" {
		return v
	}
	return "http://localhost:8081"
}

func internalKey() string {
	if v := os.Getenv("TEST_INTERNAL_KEY"); v != "" {
		return v
	}
	return "test-internal-key"
}

var httpClient = &http.Client{Timeout: 10 * time.Second}

// seedUserEmail is the ONE canonical user every test seeds. /auth/local upserts
// on email, so repeated seeds return the same user and the DB keeps exactly one
// user — which TestInternalRootTaskCreation/sole_user_default relies on. Any
// test that seeds a *different* email would break that invariant, so don't.
const seedUserEmail = "itest-user@example.com"

// do issues an internal-key request and returns (status, raw body).
func do(t *testing.T, method, path string, body any) (int, []byte) {
	t.Helper()
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, baseURL()+path, rdr)
	if err != nil {
		t.Fatalf("new request %s %s: %v", method, path, err)
	}
	req.Header.Set("X-Internal-Key", internalKey())
	req.Header.Set("Content-Type", "application/json")

	resp, err := httpClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, data
}

// doJWT issues a request with a Bearer token (for user-facing /api/tasks
// routes that authenticate via JWT rather than the internal key). Returns
// (status, raw body).
func doJWT(t *testing.T, method, path, token string, body any) (int, []byte) {
	t.Helper()
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, baseURL()+path, rdr)
	if err != nil {
		t.Fatalf("new request %s %s: %v", method, path, err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := httpClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, data
}

// doNoAuth issues a request with no auth headers (for public endpoints like
// /auth/local). Returns (status, raw body).
func doNoAuth(t *testing.T, method, path string, body any) (int, []byte) {
	t.Helper()
	var rdr io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
		rdr = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, baseURL()+path, rdr)
	if err != nil {
		t.Fatalf("new request %s %s: %v", method, path, err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := httpClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(resp.Body)
	return resp.StatusCode, data
}

// decodeJSON unmarshals a response body into T, failing the test on error.
func decodeJSON[T any](t *testing.T, data []byte) T {
	t.Helper()
	var v T
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatalf("decode: %v\nbody: %s", err, string(data))
	}
	return v
}

func ids(cs []card) []string {
	out := make([]string, 0, len(cs))
	for _, c := range cs {
		out = append(out, c.ID)
	}
	return out
}

func contains(s []string, v string) bool {
	for _, x := range s {
		if x == v {
			return true
		}
	}
	return false
}
