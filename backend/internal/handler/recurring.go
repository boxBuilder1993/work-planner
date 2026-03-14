package handler

import (
	"net/http"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

type RecurringHandler struct {
	store *store.Store
}

func NewRecurringHandler(s *store.Store) *RecurringHandler {
	return &RecurringHandler{store: s}
}

// GET /api/tasks/:id/recurring
func (h *RecurringHandler) Get(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	rt, err := h.store.GetRepeatingTask(r.Context(), userID, taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if rt == nil {
		writeError(w, http.StatusNotFound, "no recurring rule found")
		return
	}

	writeJSON(w, http.StatusOK, rt)
}

// PUT /api/tasks/:id/recurring
func (h *RecurringHandler) Upsert(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	var req model.UpsertRepeatingTaskRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	now := time.Now().UnixMilli()
	rt := &model.RepeatingTask{
		ID:              uuid.New().String(),
		TaskID:          taskID,
		RepetitionType:  req.RepetitionType,
		RepetitionProps: req.RepetitionProps,
		StartDate:       req.StartDate,
		CreatedAt:       now,
		UpdatedAt:       now,
	}

	err := h.store.UpsertRepeatingTask(r.Context(), userID, rt)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to save recurring rule")
		return
	}

	// Fetch the saved version (might be an update).
	saved, err := h.store.GetRepeatingTask(r.Context(), userID, taskID)
	if err != nil || saved == nil {
		writeJSON(w, http.StatusOK, rt)
		return
	}
	writeJSON(w, http.StatusOK, saved)
}

// DELETE /api/tasks/:id/recurring
func (h *RecurringHandler) Delete(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	err := h.store.DeleteRepeatingTask(r.Context(), userID, taskID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "no recurring rule found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete recurring rule")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// ServeHTTP routes /api/tasks/:id/recurring requests.
func (h *RecurringHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.Get(w, r)
	case http.MethodPut:
		h.Upsert(w, r)
	case http.MethodDelete:
		h.Delete(w, r)
	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}
