package worker

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/google/uuid"
)

type RecurringWorker struct {
	store *store.Store
}

func NewRecurringWorker(s *store.Store) *RecurringWorker {
	return &RecurringWorker{store: s}
}

func (w *RecurringWorker) Start(ctx context.Context) {
	// Run once on startup, then every hour.
	w.tick(ctx)

	ticker := time.NewTicker(1 * time.Hour)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Println("Recurring worker stopped")
			return
		case <-ticker.C:
			w.tick(ctx)
		}
	}
}

func (w *RecurringWorker) tick(ctx context.Context) {
	log.Println("Recurring worker: checking for tasks to create...")

	items, err := w.store.ListAllRepeatingTasksWithTemplates(ctx)
	if err != nil {
		log.Printf("Recurring worker error listing rules: %v", err)
		return
	}

	now := time.Now()
	todayStart := time.Date(now.Year(), now.Month(), now.Day(), 0, 0, 0, 0, now.Location())

	for _, item := range items {
		if err := w.processRule(ctx, item, todayStart, now); err != nil {
			log.Printf("Recurring worker error processing rule %s: %v", item.Rule.ID, err)
		}
	}
}

func (w *RecurringWorker) processRule(ctx context.Context, item store.RepeatingTaskWithTemplate, todayStart, now time.Time) error {
	if item.Rule.RepetitionType != "interval_days" {
		return nil
	}

	// Parse interval_days from repetition_props.
	var props struct {
		IntervalDays int `json:"interval_days"`
	}
	if err := json.Unmarshal(item.Rule.RepetitionProps, &props); err != nil {
		return fmt.Errorf("unmarshal repetition_props: %w", err)
	}
	if props.IntervalDays <= 0 {
		return nil
	}

	// Skip if parent is CLOSED.
	if item.Template.ParentID != nil {
		closed, err := w.store.IsTaskClosed(ctx, *item.Template.ParentID)
		if err != nil {
			return fmt.Errorf("check parent status: %w", err)
		}
		if closed {
			return nil
		}
	}

	// Calculate which dates need tasks created.
	startDate := time.UnixMilli(item.Rule.StartDate)
	interval := time.Duration(props.IntervalDays) * 24 * time.Hour

	// Find the next scheduled date after lastCreatedAt (or startDate if never created).
	var cursor time.Time
	if item.Rule.LastCreatedAt != nil {
		cursor = time.UnixMilli(*item.Rule.LastCreatedAt).Add(interval)
	} else {
		cursor = startDate
	}

	// Create tasks for all missed dates up to today.
	created := false
	for !cursor.After(todayStart) {
		taskDate := time.Date(cursor.Year(), cursor.Month(), cursor.Day(), 0, 0, 0, 0, cursor.Location())
		title := fmt.Sprintf("[%s] - %s", taskDate.Format("Jan 2, 2006"), item.Template.Title)

		nowMilli := now.UnixMilli()
		taskDateMilli := taskDate.UnixMilli()
		task := &model.Task{
			ID:          uuid.New().String(),
			UserID:      item.Template.UserID,
			ParentID:    item.Template.ParentID,
			Title:       title,
			Description: item.Template.Description,
			Status:      "PENDING",
			Priority:    item.Template.Priority,
			TaskDate:    &taskDateMilli,
			CreatedAt:   nowMilli,
			UpdatedAt:   nowMilli,
		}

		if err := w.store.CreateTask(ctx, task); err != nil {
			return fmt.Errorf("create recurring task instance: %w", err)
		}

		log.Printf("Created recurring task: %s", title)
		created = true
		cursor = cursor.Add(interval)
	}

	if created {
		// Update last_created_at to the latest date we created for.
		lastDate := cursor.Add(-interval)
		if err := w.store.UpdateRepeatingTaskLastCreated(ctx, item.Rule.ID, lastDate.UnixMilli()); err != nil {
			return fmt.Errorf("update last_created_at: %w", err)
		}
	}

	return nil
}
