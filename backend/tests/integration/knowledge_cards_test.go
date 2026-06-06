//go:build integration

package integration

import (
	"net/url"
	"strings"
	"testing"
)

// All test cards carry this tag so the suite is robust against a dirty DB
// (we scope every query to it and clean it up before + after).
const itestTag = "itest"

type card struct {
	ID        string   `json:"id"`
	Content   string   `json:"content"`
	Tags      []string `json:"tags"`
	IsValid   bool     `json:"isValid"`
	CreatedAt int64    `json:"createdAt"`
	UpdatedAt int64    `json:"updatedAt"`
}

func TestKnowledgeCards(t *testing.T) {
	// Remove any leftover itest cards (prior run against a persistent stack),
	// and again at the end so the suite leaves no trace.
	cleanup := func() {
		st, body := do(t, "GET", "/api/internal/knowledge-cards?includeInvalid=true&tag="+itestTag, nil)
		if st != 200 {
			return
		}
		for _, c := range decodeJSON[[]card](t, body) {
			do(t, "DELETE", "/api/internal/knowledge-cards/"+c.ID, nil)
		}
	}
	cleanup()
	t.Cleanup(cleanup)

	create := func(id, content string, tags ...string) (int, []byte) {
		return do(t, "POST", "/api/internal/knowledge-cards", map[string]any{
			"id":      id,
			"content": content,
			"tags":    append([]string{itestTag}, tags...),
		})
	}

	search := func(q string, extra ...string) []card {
		t.Helper()
		v := url.Values{}
		if q != "" {
			v.Set("q", q)
		}
		v.Set("tag", itestTag)
		for i := 0; i+1 < len(extra); i += 2 {
			v.Set(extra[i], extra[i+1])
		}
		st, body := do(t, "GET", "/api/internal/knowledge-cards/search?"+v.Encode(), nil)
		if st != 200 {
			t.Fatalf("search %q: status %d (%s)", q, st, body)
		}
		return decodeJSON[[]card](t, body)
	}

	// ── create ──────────────────────────────────────────────────────────
	t.Run("create", func(t *testing.T) {
		cases := []struct {
			id, content string
			tags        []string
		}{
			{"itest-auth-jwt", "Auth is JWT-based. Tokens issue at /api/auth/google, 30-day expiry, validated in middleware. No server-side sessions.", []string{"auth", "backend"}},
			{"itest-commit", "Conventional commits: feat fix chore docs. Co-Authored-By trailer for AI commits.", []string{"convention"}},
			{"itest-pipeline", "ai mentions become WorkItems. chat_handler enqueues, work_item_handler dispatches with bounded retry.", []string{"architecture", "backend"}},
		}
		for _, tc := range cases {
			if st, body := create(tc.id, tc.content, tc.tags...); st != 201 {
				t.Errorf("create %s: want 201 got %d (%s)", tc.id, st, body)
			}
		}
	})

	// ── validation ──────────────────────────────────────────────────────
	t.Run("validation", func(t *testing.T) {
		if st, _ := create("itest-auth-jwt", "dup", "x"); st != 409 {
			t.Errorf("duplicate id: want 409 got %d", st)
		}
		if st, _ := do(t, "POST", "/api/internal/knowledge-cards", map[string]any{"id": "BAD id!", "content": "x"}); st != 400 {
			t.Errorf("bad slug: want 400 got %d", st)
		}
		if st, _ := do(t, "POST", "/api/internal/knowledge-cards", map[string]any{"id": "itest-empty", "content": "   "}); st != 400 {
			t.Errorf("empty content: want 400 got %d", st)
		}
	})

	// ── list ────────────────────────────────────────────────────────────
	t.Run("list", func(t *testing.T) {
		st, body := do(t, "GET", "/api/internal/knowledge-cards?tag="+itestTag, nil)
		if st != 200 {
			t.Fatalf("list: %d", st)
		}
		if n := len(decodeJSON[[]card](t, body)); n != 3 {
			t.Errorf("list tag=itest: want 3 got %d", n)
		}
	})

	// ── search ──────────────────────────────────────────────────────────
	t.Run("search", func(t *testing.T) {
		if h := search("jwt"); len(h) != 1 || h[0].ID != "itest-auth-jwt" {
			t.Errorf("q=jwt: want [itest-auth-jwt] got %v", ids(h))
		}
		if h := search("retry dispatch"); len(h) != 1 || h[0].ID != "itest-pipeline" {
			t.Errorf("q='retry dispatch': want [itest-pipeline] got %v", ids(h))
		}
		if h := search("zzznotaword"); len(h) != 0 {
			t.Errorf("q=miss: want 0 got %v", ids(h))
		}
	})

	// ── edit + validity ─────────────────────────────────────────────────
	t.Run("edit_and_validity", func(t *testing.T) {
		st, _ := do(t, "PATCH", "/api/internal/knowledge-cards/itest-auth-jwt", map[string]any{
			"content": "UPDATED: JWT now uses a 7-day expiry.",
			"tags":    []string{itestTag, "auth", "updated"},
		})
		if st != 200 {
			t.Fatalf("patch content+tags: %d", st)
		}
		_, body := do(t, "GET", "/api/internal/knowledge-cards/itest-auth-jwt", nil)
		c := decodeJSON[card](t, body)
		if !strings.HasPrefix(c.Content, "UPDATED") || !contains(c.Tags, "updated") {
			t.Errorf("edit not persisted: %+v", c)
		}

		// mark a card invalid → excluded from default search, surfaced with includeInvalid
		do(t, "PATCH", "/api/internal/knowledge-cards/itest-commit", map[string]any{"isValid": false})
		if h := search("conventional"); len(h) != 0 {
			t.Errorf("invalid card should be excluded: got %v", ids(h))
		}
		if h := search("conventional", "includeInvalid", "true"); len(h) != 1 {
			t.Errorf("includeInvalid should surface it: got %v", ids(h))
		}
	})

	// ── get / delete / 404 ──────────────────────────────────────────────
	t.Run("get_delete_404", func(t *testing.T) {
		if st, _ := do(t, "GET", "/api/internal/knowledge-cards/itest-pipeline", nil); st != 200 {
			t.Errorf("get existing: want 200 got %d", st)
		}
		if st, _ := do(t, "GET", "/api/internal/knowledge-cards/itest-does-not-exist", nil); st != 404 {
			t.Errorf("get missing: want 404 got %d", st)
		}
		if st, _ := do(t, "DELETE", "/api/internal/knowledge-cards/itest-pipeline", nil); st != 200 {
			t.Errorf("delete: want 200 got %d", st)
		}
		if st, _ := do(t, "DELETE", "/api/internal/knowledge-cards/itest-pipeline", nil); st != 404 {
			t.Errorf("delete again: want 404 got %d", st)
		}
	})
}
