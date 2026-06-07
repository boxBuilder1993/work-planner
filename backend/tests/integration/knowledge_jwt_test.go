//go:build integration

package integration

import "testing"

type jwtCard struct {
	ID        string   `json:"id"`
	Content   string   `json:"content"`
	Tags      []string `json:"tags"`
	IsValid   bool     `json:"isValid"`
	UpdatedAt int64    `json:"updatedAt"`
}

// The web Knowledge Cards page is backed by JWT-authed /api/knowledge-cards
// endpoints (cards are global, no per-user scoping). This drives full CRUD +
// search over JWT, mirroring what the UI does.
func TestKnowledgeCardsJWT(t *testing.T) {
	st, body := doNoAuth(t, "POST", "/auth/local", map[string]any{
		"email": seedUserEmail, "name": seedUserEmail,
	})
	if st != 200 {
		t.Fatalf("auth/local: %d (%s)", st, body)
	}
	token := decodeJSON[authResp](t, body).Token

	const slug = "jwt-ui-test-card"
	t.Cleanup(func() { doJWT(t, "DELETE", "/api/knowledge-cards/"+slug, token, nil) })

	t.Run("create", func(t *testing.T) {
		st, body := doJWT(t, "POST", "/api/knowledge-cards", token, map[string]any{
			"id": slug, "content": "Cards are edited from the web UI.", "tags": []string{"ui", "test"},
		})
		if st != 201 {
			t.Fatalf("create: want 201 got %d (%s)", st, body)
		}
		c := decodeJSON[jwtCard](t, body)
		if c.ID != slug || !c.IsValid || len(c.Tags) != 2 {
			t.Errorf("created card unexpected: %+v", c)
		}
	})

	t.Run("bad_slug_rejected", func(t *testing.T) {
		st, _ := doJWT(t, "POST", "/api/knowledge-cards", token, map[string]any{
			"id": "Bad Slug", "content": "x",
		})
		if st != 400 {
			t.Errorf("bad slug: want 400 got %d", st)
		}
	})

	t.Run("list_and_search_find_it", func(t *testing.T) {
		st, body := doJWT(t, "GET", "/api/knowledge-cards", token, nil)
		if st != 200 {
			t.Fatalf("list: %d", st)
		}
		if !cardIDsContain(decodeJSON[[]jwtCard](t, body), slug) {
			t.Errorf("list should contain %s", slug)
		}
		st, body = doJWT(t, "GET", "/api/knowledge-cards/search?q=edited+from+the+web", token, nil)
		if st != 200 {
			t.Fatalf("search: %d", st)
		}
		if !cardIDsContain(decodeJSON[[]jwtCard](t, body), slug) {
			t.Errorf("search should surface %s", slug)
		}
	})

	t.Run("get", func(t *testing.T) {
		st, body := doJWT(t, "GET", "/api/knowledge-cards/"+slug, token, nil)
		if st != 200 {
			t.Fatalf("get: want 200 got %d (%s)", st, body)
		}
	})

	t.Run("update_and_invalidate", func(t *testing.T) {
		st, body := doJWT(t, "PATCH", "/api/knowledge-cards/"+slug, token, map[string]any{
			"content": "Updated from the UI.", "isValid": false,
		})
		if st != 200 {
			t.Fatalf("update: want 200 got %d (%s)", st, body)
		}
		c := decodeJSON[jwtCard](t, body)
		if c.IsValid || c.Content != "Updated from the UI." {
			t.Errorf("update didn't apply: %+v", c)
		}
		// Default list excludes invalid; includeInvalid surfaces it again.
		st, body = doJWT(t, "GET", "/api/knowledge-cards", token, nil)
		if cardIDsContain(decodeJSON[[]jwtCard](t, body), slug) {
			t.Errorf("invalid card should be excluded from default list")
		}
		st, body = doJWT(t, "GET", "/api/knowledge-cards?includeInvalid=true", token, nil)
		if !cardIDsContain(decodeJSON[[]jwtCard](t, body), slug) {
			t.Errorf("includeInvalid should surface the retired card")
		}
		_ = st
	})

	t.Run("delete_then_404", func(t *testing.T) {
		st, _ := doJWT(t, "DELETE", "/api/knowledge-cards/"+slug, token, nil)
		if st != 200 {
			t.Fatalf("delete: want 200 got %d", st)
		}
		st, _ = doJWT(t, "GET", "/api/knowledge-cards/"+slug, token, nil)
		if st != 404 {
			t.Errorf("get after delete: want 404 got %d", st)
		}
	})

	t.Run("requires_auth", func(t *testing.T) {
		// No bearer token → 401 (not the internal-key surface).
		st, _ := doNoAuth(t, "GET", "/api/knowledge-cards", nil)
		if st != 401 {
			t.Errorf("unauthenticated: want 401 got %d", st)
		}
	})
}

func cardIDsContain(cards []jwtCard, id string) bool {
	for _, c := range cards {
		if c.ID == id {
			return true
		}
	}
	return false
}
