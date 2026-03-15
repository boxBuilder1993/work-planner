package handler

import (
	"context"
	"net/http"
	"strings"

	"github.com/boxBuilder1993/work-planner/backend/internal/auth"
	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
)

// InternalHandler serves /api/internal/ endpoints for the ai-poller.
// These endpoints skip user-scoping and return tasks across all users.
type InternalHandler struct {
	store *store.Store
}

func NewInternalHandler(s *store.Store) *InternalHandler {
	return &InternalHandler{store: s}
}

// RequireInternal is middleware that rejects requests without the internal flag.
func RequireInternal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		isInternal, _ := r.Context().Value(auth.IsInternalKey).(bool)
		if !isInternal {
			writeError(w, http.StatusForbidden, "internal access required")
			return
		}
		next.ServeHTTP(w, r)
	})
}

// setUserIDFromTask looks up the task's owner and puts it on the context
// so existing user-scoped store methods work for writes.
func (h *InternalHandler) setUserIDFromTask(ctx context.Context, taskID string) (context.Context, error) {
	task, err := h.store.GetTaskByID(ctx, taskID)
	if err != nil {
		return ctx, err
	}
	if task == nil {
		return ctx, nil
	}
	return context.WithValue(ctx, auth.UserIDKey, task.UserID), nil
}

// GET /api/internal/tasks?status=...
func (h *InternalHandler) ListTasks(w http.ResponseWriter, r *http.Request) {
	var statusPtr *string
	if s := r.URL.Query().Get("status"); s != "" {
		statusPtr = &s
	}

	tasks, err := h.store.ListAllRootTasks(r.Context(), statusPtr)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
}

// GET /api/internal/tasks/{id}/children
func (h *InternalHandler) ListChildren(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3) // /api/internal/tasks/:id/children

	tasks, err := h.store.ListAllChildren(r.Context(), taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
}

// GET /api/internal/tasks/{id}/comments?type=...
func (h *InternalHandler) ListComments(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3) // /api/internal/tasks/:id/comments

	var commentType *string
	if ct := r.URL.Query().Get("type"); ct != "" {
		commentType = &ct
	}

	comments, err := h.store.ListAllComments(r.Context(), taskID, commentType)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if comments == nil {
		comments = []model.Comment{}
	}

	writeJSON(w, http.StatusOK, comments)
}

// ServeHTTP routes /api/internal/ requests.
func (h *InternalHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")

	switch {
	// GET /api/internal/tasks
	case r.Method == http.MethodGet && path == "/api/internal/tasks":
		h.ListTasks(w, r)

	// GET /api/internal/tasks/:id/children
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/children"):
		h.ListChildren(w, r)

	// GET /api/internal/tasks/:id/comments
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/comments"):
		h.ListComments(w, r)

	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}
