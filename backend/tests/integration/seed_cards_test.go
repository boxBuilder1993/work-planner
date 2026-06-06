//go:build integration

package integration

import "testing"

// The e2e stack runs all migrations on a fresh DB, so the baseline seed cards
// (migration 009) must be present and searchable.
func TestSeededKnowledgeCards(t *testing.T) {
	expected := []string{
		"ai-orchestration-overview",
		"ai-personas",
		"knowledge-cards-system",
		"persona-tools",
		"wp-cli",
		"work-items",
	}

	t.Run("each_seed_card_present", func(t *testing.T) {
		for _, slug := range expected {
			st, body := do(t, "GET", "/api/internal/knowledge-cards/"+slug, nil)
			if st != 200 {
				t.Errorf("seed card %s: want 200 got %d (%s)", slug, st, body)
			}
		}
	})

	t.Run("seed_cards_are_searchable", func(t *testing.T) {
		// FTS over the seeded content works (and excludes nothing — they're valid).
		st, body := do(t, "GET", "/api/internal/knowledge-cards/search?q=persona", nil)
		if st != 200 {
			t.Fatalf("search: %d", st)
		}
		hits := ids(decodeJSON[[]card](t, body))
		if !contains(hits, "ai-personas") {
			t.Errorf("search 'persona' should surface the ai-personas seed card; got %v", hits)
		}
	})

	t.Run("dev_only_cards_not_seeded", func(t *testing.T) {
		// Work-planner development cards (e.g. commit-convention, repo layout)
		// are intentionally NOT in the baseline seed.
		for _, slug := range []string{"commit-convention", "workplanner-repo-layout", "make-targets"} {
			st, _ := do(t, "GET", "/api/internal/knowledge-cards/"+slug, nil)
			if st != 404 {
				t.Errorf("dev card %s should NOT be seeded; got status %d", slug, st)
			}
		}
	})
}
