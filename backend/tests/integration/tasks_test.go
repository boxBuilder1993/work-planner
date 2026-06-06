//go:build integration

package integration

import (
	"net/http"
	"testing"
)

type task struct {
	ID       string  `json:"id"`
	UserID   string  `json:"userId"`
	ParentID *string `json:"parentId"`
	Title    string  `json:"title"`
}

type authResp struct {
	Token string `json:"token"`
	User  struct {
		ID    string `json:"id"`
		Email string `json:"email"`
	} `json:"user"`
}

// seedUser creates a user via the local-auth endpoint (unauthenticated) and
// returns its id. Root-task creation needs a user to own the task
// (tasks.user_id is a FK), and the internal API has no JWT to infer one.
func seedUser(t *testing.T, email string) string {
	t.Helper()
	st, body := doNoAuth(t, "POST", "/auth/local", map[string]any{"email": email, "name": email})
	if st != 200 {
		t.Fatalf("seed user %s: status %d (%s)", email, st, body)
	}
	a := decodeJSON[authResp](t, body)
	if a.User.ID == "" {
		t.Fatalf("seed user %s: no user id in response: %s", email, body)
	}
	return a.User.ID
}

func TestInternalRootTaskCreation(t *testing.T) {
	owner := seedUser(t, "root-task-test@example.com")

	cleanup := func(id string) {
		if id != "" {
			do(t, "DELETE", "/api/internal/tasks/"+id, nil)
		}
	}

	t.Run("explicit_ownerId", func(t *testing.T) {
		st, body := do(t, "POST", "/api/internal/tasks", map[string]any{
			"title":   "itest root via ownerId",
			"ownerId": owner,
		})
		if st != 201 {
			t.Fatalf("create root with ownerId: want 201 got %d (%s)", st, body)
		}
		tk := decodeJSON[task](t, body)
		t.Cleanup(func() { cleanup(tk.ID) })
		if tk.ParentID != nil {
			t.Errorf("root task should have null parentId, got %v", *tk.ParentID)
		}
		if tk.UserID != owner {
			t.Errorf("root task owner: want %s got %s", owner, tk.UserID)
		}
	})

	t.Run("sole_user_default", func(t *testing.T) {
		// No parentId, no ownerId — with exactly one user seeded, the backend
		// defaults the owner to that sole user.
		st, body := do(t, "POST", "/api/internal/tasks", map[string]any{
			"title": "itest root via sole-user default",
		})
		if st != 201 {
			t.Fatalf("create root (sole-user default): want 201 got %d (%s)", st, body)
		}
		tk := decodeJSON[task](t, body)
		t.Cleanup(func() { cleanup(tk.ID) })
		if tk.ParentID != nil {
			t.Errorf("root task should have null parentId, got %v", *tk.ParentID)
		}
		if tk.UserID != owner {
			t.Errorf("sole-user default owner: want %s got %s", owner, tk.UserID)
		}
	})

	t.Run("bogus_ownerId_rejected", func(t *testing.T) {
		st, _ := do(t, "POST", "/api/internal/tasks", map[string]any{
			"title":   "itest bad owner",
			"ownerId": "00000000-0000-0000-0000-000000000000",
		})
		if st != http.StatusBadRequest {
			t.Errorf("bogus ownerId: want 400 got %d", st)
		}
	})

	t.Run("child_still_derives_owner_from_parent", func(t *testing.T) {
		// Create a root, then a child with no ownerId — child inherits owner.
		_, body := do(t, "POST", "/api/internal/tasks", map[string]any{
			"title": "itest parent", "ownerId": owner,
		})
		parent := decodeJSON[task](t, body)
		t.Cleanup(func() { cleanup(parent.ID) })

		st, cbody := do(t, "POST", "/api/internal/tasks", map[string]any{
			"title": "itest child", "parentId": parent.ID,
		})
		if st != 201 {
			t.Fatalf("create child: want 201 got %d (%s)", st, cbody)
		}
		child := decodeJSON[task](t, cbody)
		t.Cleanup(func() { cleanup(child.ID) })
		if child.ParentID == nil || *child.ParentID != parent.ID {
			t.Errorf("child parentId: want %s got %v", parent.ID, child.ParentID)
		}
		if child.UserID != owner {
			t.Errorf("child owner derived from parent: want %s got %s", owner, child.UserID)
		}
	})
}
