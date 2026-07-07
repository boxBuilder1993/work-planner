//go:build integration

package integration

import (
	"fmt"
	"testing"
	"time"
)

// End-to-end coverage for email+password auth: register, login, generic
// failure, duplicate email, weak password, and the "existing (passwordless)
// user sets a password then logs in" flow.
func TestPasswordAuth(t *testing.T) {
	uniq := time.Now().UnixNano()
	email := fmt.Sprintf("pwauth-%d@itest.local", uniq)
	const pw = "integration-secret-123"

	st, body := doNoAuth(t, "POST", "/auth/register", map[string]any{"email": email, "name": "IT", "password": pw})
	if st != 200 {
		t.Fatalf("register: want 200 got %d (%s)", st, body)
	}
	if reg := decodeJSON[authResp](t, body); reg.Token == "" {
		t.Errorf("register should return a token")
	}

	t.Run("login_ok", func(t *testing.T) {
		if s, _ := doNoAuth(t, "POST", "/auth/login", map[string]any{"email": email, "password": pw}); s != 200 {
			t.Errorf("want 200 got %d", s)
		}
	})
	t.Run("login_wrong_password", func(t *testing.T) {
		if s, _ := doNoAuth(t, "POST", "/auth/login", map[string]any{"email": email, "password": "not-it"}); s != 401 {
			t.Errorf("want 401 got %d", s)
		}
	})
	t.Run("login_unknown_email", func(t *testing.T) {
		if s, _ := doNoAuth(t, "POST", "/auth/login", map[string]any{"email": "nobody@itest.local", "password": pw}); s != 401 {
			t.Errorf("want 401 got %d", s)
		}
	})
	t.Run("register_duplicate", func(t *testing.T) {
		if s, _ := doNoAuth(t, "POST", "/auth/register", map[string]any{"email": email, "name": "x", "password": pw}); s != 409 {
			t.Errorf("want 409 got %d", s)
		}
	})
	t.Run("register_weak_password", func(t *testing.T) {
		e := fmt.Sprintf("weak-%d@itest.local", uniq)
		if s, _ := doNoAuth(t, "POST", "/auth/register", map[string]any{"email": e, "name": "x", "password": "short"}); s != 400 {
			t.Errorf("want 400 got %d", s)
		}
	})

	// Existing passwordless account (created via local auth) can set a password
	// from an authenticated session, then log in with it — the production path.
	t.Run("set_password_then_login", func(t *testing.T) {
		lemail := fmt.Sprintf("existing-%d@itest.local", uniq)
		s, lb := doNoAuth(t, "POST", "/auth/local", map[string]any{"email": lemail, "name": "Existing"})
		if s != 200 {
			t.Fatalf("local auth: want 200 got %d (%s)", s, lb)
		}
		la := decodeJSON[authResp](t, lb)

		if s, _ := doNoAuth(t, "POST", "/auth/login", map[string]any{"email": lemail, "password": "brand-new-pass"}); s != 401 {
			t.Errorf("passwordless login should 401, got %d", s)
		}
		if s, _ := doJWT(t, "POST", "/auth/password", la.Token, map[string]any{"password": "brand-new-pass"}); s != 200 {
			t.Errorf("set-password: want 200 got %d", s)
		}
		if s, _ := doNoAuth(t, "POST", "/auth/login", map[string]any{"email": lemail, "password": "brand-new-pass"}); s != 200 {
			t.Errorf("login after set-password: want 200 got %d", s)
		}
	})
}
