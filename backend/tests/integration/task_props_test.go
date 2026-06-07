//go:build integration

package integration

import "testing"

// taskWithProps decodes the props field that the task scanners must return.
type taskWithProps struct {
	ID    string         `json:"id"`
	Props map[string]any `json:"props"`
}

// Regression for the missing-t.props bug: GetBreadcrumbs and ListExecutableTasks
// (and the recurring-task worker query) selected 15 task columns while the task
// scanner reads 16 (including props) — so they didn't merely drop props, they
// errored: ListExecutableTasks failed the scan, and GetBreadcrumbs' recursive
// CTE had a UNION column-count mismatch. These exercise the two HTTP-reachable
// queries end-to-end and assert props comes back. Before the fix both 500.
func TestTaskPropsInBreadcrumbsAndExecutable(t *testing.T) {
	// JWT auth — /api/tasks/* are user-facing routes.
	st, body := doNoAuth(t, "POST", "/auth/local", map[string]any{
		"email": seedUserEmail, "name": seedUserEmail,
	})
	if st != 200 {
		t.Fatalf("auth/local: %d (%s)", st, body)
	}
	auth := decodeJSON[authResp](t, body)
	owner, token := auth.User.ID, auth.Token

	// Root task WITH props, then a leaf child under it.
	_, pb := do(t, "POST", "/api/internal/tasks", map[string]any{
		"title": "props-parent", "ownerId": owner,
		"props": map[string]any{"algorithm": "orchestrated", "marker": "PROPS_OK"},
	})
	parent := decodeJSON[task](t, pb)
	t.Cleanup(func() { do(t, "DELETE", "/api/internal/tasks/"+parent.ID, nil) })

	_, cb := do(t, "POST", "/api/internal/tasks", map[string]any{
		"title": "props-child", "parentId": parent.ID,
	})
	child := decodeJSON[task](t, cb)
	t.Cleanup(func() { do(t, "DELETE", "/api/internal/tasks/"+child.ID, nil) })

	t.Run("breadcrumbs_succeeds_and_returns_props", func(t *testing.T) {
		st, body := doJWT(t, "GET", "/api/tasks/"+child.ID+"/breadcrumbs", token, nil)
		if st != 200 {
			t.Fatalf("breadcrumbs: want 200 got %d (%s)", st, body)
		}
		chain := decodeJSON[[]taskWithProps](t, body)
		var found bool
		for _, tk := range chain {
			if tk.ID == parent.ID {
				found = true
				if tk.Props["marker"] != "PROPS_OK" {
					t.Errorf("parent breadcrumb should carry props; got %v", tk.Props)
				}
			}
		}
		if !found {
			t.Errorf("parent %s missing from breadcrumb chain", parent.ID)
		}
	})

	t.Run("executable_succeeds_and_includes_leaf", func(t *testing.T) {
		st, body := doJWT(t, "GET", "/api/tasks/executable", token, nil)
		if st != 200 {
			t.Fatalf("executable: want 200 got %d (%s)", st, body)
		}
		tasks := decodeJSON[[]taskWithProps](t, body)
		var foundChild bool
		for _, tk := range tasks {
			if tk.ID == child.ID {
				foundChild = true // and it decoded with a props field present
			}
		}
		if !foundChild {
			t.Errorf("PENDING leaf child %s should be in the executable list", child.ID)
		}
	})
}
