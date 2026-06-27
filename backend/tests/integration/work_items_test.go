//go:build integration

package integration

import "testing"

type workItem struct {
	ID             string  `json:"id"`
	TaskID         string  `json:"taskId"`
	TargetPersona  string  `json:"targetPersona"`
	Status         string  `json:"status"`
	IdempotencyKey *string `json:"idempotencyKey"`
}

// Driver (sweep-created) WorkItems carry no triggering comment, so they dedupe
// on an explicit idempotency_key. This is what lets the heartbeat enqueue
// "drive all aiMonitoring tasks" every poll cycle while collapsing to one
// driver per (task, 5-min bucket): the first create inserts (201); a second
// with the same key returns the existing row (200, same id); a different key
// makes a distinct WorkItem.
func TestWorkItemIdempotencyKey(t *testing.T) {
	owner := seedUser(t, seedUserEmail)

	_, body := do(t, "POST", "/api/internal/tasks", map[string]any{
		"title": "itest driver idempotency", "ownerId": owner,
	})
	tk := decodeJSON[task](t, body)
	t.Cleanup(func() { do(t, "DELETE", "/api/internal/tasks/"+tk.ID, nil) })

	key := "driver:" + tk.ID + ":99999"
	create := func(idemKey string) (int, workItem) {
		st, b := do(t, "POST", "/api/internal/work-items", map[string]any{
			"taskId":         tk.ID,
			"targetPersona":  "driver",
			"idempotencyKey": idemKey,
		})
		return st, decodeJSON[workItem](t, b)
	}

	st1, w1 := create(key)
	if st1 != 201 {
		t.Fatalf("first create: want 201 got %d", st1)
	}

	t.Run("same_key_returns_existing", func(t *testing.T) {
		st2, w2 := create(key)
		if st2 != 200 {
			t.Errorf("second create (same key): want 200 (existing) got %d", st2)
		}
		if w2.ID != w1.ID {
			t.Errorf("dedupe failed: second create returned a different WorkItem (%s != %s)", w2.ID, w1.ID)
		}
	})

	t.Run("different_key_creates_new", func(t *testing.T) {
		st3, w3 := create(key + "-other")
		if st3 != 201 {
			t.Errorf("distinct key: want 201 got %d", st3)
		}
		if w3.ID == w1.ID {
			t.Errorf("distinct key should create a new WorkItem, got same id %s", w3.ID)
		}
	})
}
