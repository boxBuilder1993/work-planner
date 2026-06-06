//go:build integration

package integration

import "testing"

type comment struct {
	ID    string         `json:"id"`
	Text  string         `json:"text"`
	Props map[string]any `json:"props"`
}

// The archivist sweep polls GET /api/internal/comments?needs_archival=true for
// comments it hasn't reviewed yet (props 'archivist-reviewed' unset). Once the
// poller marks a comment reviewed, it must drop out of the result. Migration
// 010 marks all pre-existing comments reviewed, so a fresh comment created
// here (after migrations) is the unit under test.
func TestCommentsNeedingArchival(t *testing.T) {
	owner := seedUser(t, seedUserEmail)

	// A task to hang comments on.
	_, body := do(t, "POST", "/api/internal/tasks", map[string]any{
		"title": "itest archivist", "ownerId": owner,
	})
	tk := decodeJSON[task](t, body)
	t.Cleanup(func() { do(t, "DELETE", "/api/internal/tasks/"+tk.ID, nil) })

	// Create an un-reviewed comment.
	st, cbody := do(t, "POST", "/api/internal/tasks/"+tk.ID+"/comments", map[string]any{
		"text":      "We settled on Postgres FTS, not a vector store.",
		"createdBy": "user",
	})
	if st != 201 {
		t.Fatalf("create comment: want 201 got %d (%s)", st, cbody)
	}
	c := decodeJSON[comment](t, cbody)

	archivalIDs := func(limit string) []string {
		path := "/api/internal/comments?needs_archival=true&limit=" + limit
		st, body := do(t, "GET", path, nil)
		if st != 200 {
			t.Fatalf("needs_archival: want 200 got %d (%s)", st, body)
		}
		cs := decodeJSON[[]comment](t, body)
		out := make([]string, 0, len(cs))
		for _, x := range cs {
			out = append(out, x.ID)
		}
		return out
	}

	t.Run("unreviewed_comment_surfaces", func(t *testing.T) {
		if !contains(archivalIDs("200"), c.ID) {
			t.Errorf("freshly-created comment %s should need archival", c.ID)
		}
	})

	t.Run("limit_caps_results", func(t *testing.T) {
		if got := archivalIDs("1"); len(got) != 1 {
			t.Errorf("limit=1 should cap to 1 result, got %d", len(got))
		}
	})

	t.Run("marking_reviewed_drops_it", func(t *testing.T) {
		st, body := do(t, "PATCH", "/api/internal/comments/"+c.ID, map[string]any{
			"props": map[string]any{"archivist-reviewed": true},
		})
		if st != 200 {
			t.Fatalf("mark reviewed: want 200 got %d (%s)", st, body)
		}
		if contains(archivalIDs("200"), c.ID) {
			t.Errorf("reviewed comment %s must not need archival", c.ID)
		}
	})
}
