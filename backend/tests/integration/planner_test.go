//go:build integration

package integration

import "testing"

type person struct {
	ID          string  `json:"id"`
	Name        string  `json:"name"`
	HoursPerDay float64 `json:"hoursPerDay"`
	Active      bool    `json:"active"`
}

type timeOff struct {
	ID       string   `json:"id"`
	StartDay string   `json:"startDay"`
	EndDay   string   `json:"endDay"`
	HoursOff *float64 `json:"hoursOff"`
}

type calendarObj struct {
	ID          string `json:"id"`
	WeekendDays int    `json:"weekendDays"`
}

type holiday struct {
	ID   string `json:"id"`
	Day  string `json:"day"`
	Name *string `json:"name"`
}

type dependency struct {
	ID          string `json:"id"`
	TaskID      string `json:"taskId"`
	DependsOnID string `json:"dependsOnId"`
}

// Planner people pool: create / list / update / delete + per-person time off.
func TestPlannerPeople(t *testing.T) {
	owner := seedUser(t, seedUserEmail)

	st, body := do(t, "POST", "/api/internal/people", map[string]any{
		"userId": owner, "name": "Alice", "hoursPerDay": 8,
	})
	if st != 201 {
		t.Fatalf("create person: want 201 got %d (%s)", st, body)
	}
	p := decodeJSON[person](t, body)
	t.Cleanup(func() { do(t, "DELETE", "/api/internal/people/"+p.ID, nil) })
	if p.Name != "Alice" || p.HoursPerDay != 8 || !p.Active {
		t.Fatalf("unexpected person: %+v", p)
	}

	t.Run("list", func(t *testing.T) {
		_, b := do(t, "GET", "/api/internal/people?user_id="+owner, nil)
		ppl := decodeJSON[[]person](t, b)
		found := false
		for _, x := range ppl {
			if x.ID == p.ID {
				found = true
			}
		}
		if !found {
			t.Errorf("created person %s not in list", p.ID)
		}
	})

	t.Run("update_hours", func(t *testing.T) {
		st, b := do(t, "PATCH", "/api/internal/people/"+p.ID, map[string]any{"hoursPerDay": 6})
		if st != 200 {
			t.Fatalf("update: want 200 got %d (%s)", st, b)
		}
		up := decodeJSON[person](t, b)
		if up.HoursPerDay != 6 {
			t.Errorf("hoursPerDay want 6 got %v", up.HoursPerDay)
		}
	})

	t.Run("time_off_full_and_half_day", func(t *testing.T) {
		// full-day range
		st, b := do(t, "POST", "/api/internal/people/"+p.ID+"/time-off", map[string]any{
			"startDay": "2026-07-03", "endDay": "2026-07-05",
		})
		if st != 201 {
			t.Fatalf("create time off: want 201 got %d (%s)", st, b)
		}
		full := decodeJSON[timeOff](t, b)
		if full.HoursOff != nil {
			t.Errorf("full day off should have null hoursOff, got %v", *full.HoursOff)
		}
		// half-day
		_, b2 := do(t, "POST", "/api/internal/people/"+p.ID+"/time-off", map[string]any{
			"startDay": "2026-07-10", "endDay": "2026-07-10", "hoursOff": 4,
		})
		half := decodeJSON[timeOff](t, b2)
		if half.HoursOff == nil || *half.HoursOff != 4 {
			t.Errorf("half day want hoursOff=4, got %v", half.HoursOff)
		}

		_, lb := do(t, "GET", "/api/internal/people/"+p.ID+"/time-off", nil)
		offs := decodeJSON[[]timeOff](t, lb)
		if len(offs) != 2 {
			t.Errorf("want 2 time-off entries, got %d", len(offs))
		}

		st, _ = do(t, "DELETE", "/api/internal/time-off/"+full.ID, nil)
		if st != 200 {
			t.Errorf("delete time off: want 200 got %d", st)
		}
	})

	t.Run("delete", func(t *testing.T) {
		st, _ := do(t, "DELETE", "/api/internal/people/"+p.ID, nil)
		if st != 200 {
			t.Errorf("delete person: want 200 got %d", st)
		}
	})
}

// Shared calendar: default created on first GET, weekend update, holidays CRUD.
func TestPlannerCalendar(t *testing.T) {
	owner := seedUser(t, seedUserEmail)

	st, b := do(t, "GET", "/api/internal/calendar?user_id="+owner, nil)
	if st != 200 {
		t.Fatalf("get calendar: want 200 got %d (%s)", st, b)
	}
	cal := decodeJSON[calendarObj](t, b)
	if cal.WeekendDays != 96 {
		t.Errorf("default weekendDays want 96 (Sat+Sun) got %d", cal.WeekendDays)
	}

	t.Run("update_weekend", func(t *testing.T) {
		st, b := do(t, "PUT", "/api/internal/calendar", map[string]any{"userId": owner, "weekendDays": 64})
		if st != 200 {
			t.Fatalf("upsert calendar: want 200 got %d (%s)", st, b)
		}
		if decodeJSON[calendarObj](t, b).WeekendDays != 64 {
			t.Errorf("weekendDays not updated")
		}
	})

	t.Run("holidays", func(t *testing.T) {
		name := "Diwali"
		st, b := do(t, "POST", "/api/internal/calendar/"+cal.ID+"/holidays", map[string]any{
			"day": "2026-11-08", "name": name,
		})
		if st != 201 {
			t.Fatalf("create holiday: want 201 got %d (%s)", st, b)
		}
		hol := decodeJSON[holiday](t, b)
		if hol.Day != "2026-11-08" {
			t.Errorf("holiday day want 2026-11-08 got %s", hol.Day)
		}
		_, lb := do(t, "GET", "/api/internal/calendar/"+cal.ID+"/holidays", nil)
		if len(decodeJSON[[]holiday](t, lb)) == 0 {
			t.Errorf("holiday not listed")
		}
		st, _ = do(t, "DELETE", "/api/internal/holidays/"+hol.ID, nil)
		if st != 200 {
			t.Errorf("delete holiday: want 200 got %d", st)
		}
	})
}

// Dependency DAG: create, list, cycle rejection, delete.
func TestPlannerDependencies(t *testing.T) {
	owner := seedUser(t, seedUserEmail)

	mk := func(title string) task {
		_, b := do(t, "POST", "/api/internal/tasks", map[string]any{"title": title, "ownerId": owner})
		tk := decodeJSON[task](t, b)
		t.Cleanup(func() { do(t, "DELETE", "/api/internal/tasks/"+tk.ID, nil) })
		return tk
	}
	a := mk("itest dep A")
	b := mk("itest dep B")

	// A blocked-by B
	st, body := do(t, "POST", "/api/internal/tasks/"+a.ID+"/dependencies", map[string]any{"dependsOnId": b.ID})
	if st != 201 {
		t.Fatalf("create dep: want 201 got %d (%s)", st, body)
	}
	dep := decodeJSON[dependency](t, body)

	t.Run("list", func(t *testing.T) {
		_, lb := do(t, "GET", "/api/internal/tasks/"+a.ID+"/dependencies", nil)
		deps := decodeJSON[[]dependency](t, lb)
		if len(deps) != 1 || deps[0].DependsOnID != b.ID {
			t.Errorf("expected A blocked-by B, got %+v", deps)
		}
	})

	t.Run("cycle_rejected", func(t *testing.T) {
		// B blocked-by A would close the loop A→B→A
		st, _ := do(t, "POST", "/api/internal/tasks/"+b.ID+"/dependencies", map[string]any{"dependsOnId": a.ID})
		if st != 409 {
			t.Errorf("cycle should be rejected with 409, got %d", st)
		}
	})

	t.Run("self_dep_rejected", func(t *testing.T) {
		st, _ := do(t, "POST", "/api/internal/tasks/"+a.ID+"/dependencies", map[string]any{"dependsOnId": a.ID})
		if st != 409 {
			t.Errorf("self-dependency should be rejected with 409, got %d", st)
		}
	})

	t.Run("delete", func(t *testing.T) {
		st, _ := do(t, "DELETE", "/api/internal/dependencies/"+dep.ID, nil)
		if st != 200 {
			t.Errorf("delete dep: want 200 got %d", st)
		}
	})
}
