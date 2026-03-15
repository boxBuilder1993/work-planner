package handler

import (
	"net/http"
	"strings"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

type TaskHandler struct {
	store *store.Store
}

func NewTaskHandler(s *store.Store) *TaskHandler {
	return &TaskHandler{store: s}
}

// POST /api/tasks
func (h *TaskHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req model.CreateTaskRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	now := time.Now().UnixMilli()
	priority := 0
	if req.Priority != nil {
		priority = *req.Priority
	}

	aiEnabled := false
	if req.AiEnabled != nil {
		aiEnabled = *req.AiEnabled
	}

	task := &model.Task{
		ID:          uuid.New().String(),
		UserID:      getUserID(r),
		ParentID:    req.ParentID,
		Title:       req.Title,
		Description: req.Description,
		Status:      "PENDING",
		Priority:    priority,
		DueDate:     req.DueDate,
		PlannedTime: req.PlannedTime,
		Duration:    req.Duration,
		AiEnabled:   aiEnabled,
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	if err := h.store.CreateTask(r.Context(), task); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to create task")
		return
	}

	writeJSON(w, http.StatusCreated, task)
}

// GET /api/tasks/:id
func (h *TaskHandler) Get(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2) // /api/tasks/:id
	userID := getUserID(r)

	task, err := h.store.GetTask(r.Context(), userID, taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if task == nil {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}

	writeJSON(w, http.StatusOK, task)
}

// PATCH /api/tasks/:id
func (h *TaskHandler) Update(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	var req model.UpdateTaskRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	task, err := h.store.UpdateTask(r.Context(), userID, taskID, &req, time.Now().UnixMilli())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to update task")
		return
	}
	if task == nil {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}

	writeJSON(w, http.StatusOK, task)
}

// DELETE /api/tasks/:id
func (h *TaskHandler) Delete(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	err := h.store.DeleteTask(r.Context(), userID, taskID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete task")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// GET /api/tasks?root=true&status=PENDING
func (h *TaskHandler) List(w http.ResponseWriter, r *http.Request) {
	userID := getUserID(r)
	status := r.URL.Query().Get("status")

	var statusPtr *string
	if status != "" {
		statusPtr = &status
	}

	tasks, err := h.store.ListRootTasks(r.Context(), userID, statusPtr)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
}

// GET /api/tasks/:id/children
func (h *TaskHandler) Children(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	tasks, err := h.store.ListChildren(r.Context(), userID, taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
}

// GET /api/tasks/:id/breadcrumbs
func (h *TaskHandler) Breadcrumbs(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	tasks, err := h.store.GetBreadcrumbs(r.Context(), userID, taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
}

// GET /api/tasks/executable
func (h *TaskHandler) Executable(w http.ResponseWriter, r *http.Request) {
	userID := getUserID(r)

	tasks, err := h.store.ListExecutableTasks(r.Context(), userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
}

// GET /api/tasks/search?q=...
func (h *TaskHandler) Search(w http.ResponseWriter, r *http.Request) {
	userID := getUserID(r)
	q := r.URL.Query().Get("q")
	if q == "" {
		writeJSON(w, http.StatusOK, []model.Task{})
		return
	}

	tasks, err := h.store.SearchTasks(r.Context(), userID, q)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
}

// ServeHTTP routes task requests.
func (h *TaskHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")

	switch {
	// GET /api/tasks/executable
	case r.Method == http.MethodGet && path == "/api/tasks/executable":
		h.Executable(w, r)

	// GET /api/tasks/search?q=...
	case r.Method == http.MethodGet && path == "/api/tasks/search":
		h.Search(w, r)

	// GET /api/tasks (list root)
	case r.Method == http.MethodGet && path == "/api/tasks":
		h.List(w, r)

	// POST /api/tasks
	case r.Method == http.MethodPost && path == "/api/tasks":
		h.Create(w, r)

	// GET /api/tasks/:id/children
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/children"):
		h.Children(w, r)

	// GET /api/tasks/:id/breadcrumbs
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/breadcrumbs"):
		h.Breadcrumbs(w, r)

	// GET/PUT/DELETE /api/tasks/:id/recurring — handled by RepeatingTaskHandler
	// GET/POST /api/tasks/:id/comments — handled by CommentHandler

	// GET /api/tasks/:id
	case r.Method == http.MethodGet && strings.Count(path, "/") == 3:
		h.Get(w, r)

	// PATCH /api/tasks/:id
	case r.Method == http.MethodPatch && strings.Count(path, "/") == 3:
		h.Update(w, r)

	// DELETE /api/tasks/:id
	case r.Method == http.MethodDelete && strings.Count(path, "/") == 3:
		h.Delete(w, r)

	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}
