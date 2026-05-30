package handler

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/auth"
	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
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

// GET /api/internal/tasks/search?status=...&aiStatus=...&algorithm=...&aiEnabled=true
func (h *InternalHandler) SearchTasks(w http.ResponseWriter, r *http.Request) {
	var statusPtr, aiStatusPtr, algorithmPtr *string
	var aiEnabledPtr *bool

	if s := r.URL.Query().Get("status"); s != "" {
		statusPtr = &s
	}
	if s := r.URL.Query().Get("aiStatus"); s != "" {
		aiStatusPtr = &s
	}
	if s := r.URL.Query().Get("algorithm"); s != "" {
		algorithmPtr = &s
	}
	if s := r.URL.Query().Get("aiEnabled"); s != "" {
		val := s == "true"
		aiEnabledPtr = &val
	}

	tasks, err := h.store.SearchAllTasks(r.Context(), statusPtr, aiStatusPtr, algorithmPtr, aiEnabledPtr)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if tasks == nil {
		tasks = []model.Task{}
	}

	writeJSON(w, http.StatusOK, tasks)
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

// GET /api/internal/tasks/{id}
func (h *InternalHandler) GetTask(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3) // /api/internal/tasks/:id
	task, err := h.store.GetTaskByID(r.Context(), taskID)
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

// DELETE /api/internal/tasks/{id}
func (h *InternalHandler) DeleteTask(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3)
	ctx, err := h.setUserIDFromTask(r.Context(), taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	userID, _ := ctx.Value(auth.UserIDKey).(string)
	if userID == "" {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}

	err = h.store.DeleteTask(ctx, userID, taskID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete task")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": taskID})
}

// PATCH /api/internal/tasks/{id}
func (h *InternalHandler) UpdateTask(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3)
	ctx, err := h.setUserIDFromTask(r.Context(), taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	userID, _ := ctx.Value(auth.UserIDKey).(string)

	var req model.UpdateTaskRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	task, err := h.store.UpdateTask(ctx, userID, taskID, &req, time.Now().UnixMilli())
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

// POST /api/internal/tasks/{id}/comments
func (h *InternalHandler) CreateComment(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3)
	ctx, err := h.setUserIDFromTask(r.Context(), taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	userID, _ := ctx.Value(auth.UserIDKey).(string)

	var req model.CreateCommentRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Text == "" {
		writeError(w, http.StatusBadRequest, "text is required")
		return
	}

	commentType := req.CommentType
	if commentType == "" {
		commentType = "COMMENT"
	}
	createdBy := req.CreatedBy
	if createdBy == "" {
		createdBy = "user"
	}

	now := time.Now().UnixMilli()
	var proposalStatus *string
	if commentType == "PROPOSAL" {
		s := "PENDING"
		proposalStatus = &s
	}

	comment := &model.Comment{
		ID:              uuid.New().String(),
		TaskID:          taskID,
		ParentCommentID: req.ParentCommentID,
		Text:            req.Text,
		CommentType:     commentType,
		CreatedBy:       createdBy,
		ProposalStatus:  proposalStatus,
		Props:           req.Props,
		CreatedAt:       now,
		UpdatedAt:       now,
	}

	err = h.store.CreateComment(ctx, userID, comment)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to create comment")
		return
	}
	writeJSON(w, http.StatusCreated, comment)
}

// POST /api/internal/tasks — create a task (inherits user from parent)
func (h *InternalHandler) CreateTask(w http.ResponseWriter, r *http.Request) {
	var req model.CreateTaskRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Title == "" {
		writeError(w, http.StatusBadRequest, "title is required")
		return
	}

	// Resolve user ID from parent task
	var userID string
	if req.ParentID != nil {
		parent, err := h.store.GetTaskByID(r.Context(), *req.ParentID)
		if err != nil || parent == nil {
			writeError(w, http.StatusBadRequest, "parent task not found")
			return
		}
		userID = parent.UserID
	} else {
		writeError(w, http.StatusBadRequest, "parentId is required for internal task creation")
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
	props := json.RawMessage("{}")
	if req.Props != nil {
		props = req.Props
	}

	task := &model.Task{
		ID:          uuid.New().String(),
		UserID:      userID,
		ParentID:    req.ParentID,
		Title:       req.Title,
		Description: req.Description,
		Status:      "PENDING",
		Priority:    priority,
		DueDate:     req.DueDate,
		PlannedTime: req.PlannedTime,
		Duration:    req.Duration,
		AiEnabled:   aiEnabled,
		Props:       props,
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	if err := h.store.CreateTask(r.Context(), task); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to create task")
		return
	}

	writeJSON(w, http.StatusCreated, task)
}

// PATCH /api/internal/comments/:id
// Partial update of a comment. Currently supports text edits and partial-merge
// updates to props (top-level keys replace; arrays replaced wholesale).
func (h *InternalHandler) UpdateComment(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")
	parts := strings.Split(path, "/")
	if len(parts) < 5 {
		writeError(w, http.StatusBadRequest, "invalid path")
		return
	}
	commentID := parts[4]

	var req model.UpdateCommentRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	comment, err := h.store.UpdateComment(r.Context(), commentID, &req, time.Now().UnixMilli())
	if err != nil {
		log.Printf("UpdateComment(%s): %v", commentID, err)
		writeError(w, http.StatusInternalServerError, "failed to update comment")
		return
	}
	if comment == nil {
		writeError(w, http.StatusNotFound, "comment not found")
		return
	}
	writeJSON(w, http.StatusOK, comment)
}

// GET /api/internal/comments?needs_ai_reply=true
// Returns comments containing an @ai mention with no ai-comment-status set yet.
func (h *InternalHandler) ListCommentsNeedingAIReply(w http.ResponseWriter, r *http.Request) {
	comments, err := h.store.ListCommentsNeedingAIReply(r.Context())
	if err != nil {
		log.Printf("ListCommentsNeedingAIReply: %v", err)
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if comments == nil {
		comments = []model.Comment{}
	}
	writeJSON(w, http.StatusOK, comments)
}

// POST /api/internal/comments/:id/approve
func (h *InternalHandler) ApproveProposal(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")
	// /api/internal/comments/:id/approve → segment 4 is the ID
	parts := strings.Split(path, "/")
	if len(parts) < 5 {
		writeError(w, http.StatusBadRequest, "invalid path")
		return
	}
	commentID := parts[4]

	comment, err := h.store.UpdateProposalStatusUnscoped(r.Context(), commentID, "APPROVED", nil, time.Now().UnixMilli())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to approve proposal")
		return
	}
	if comment == nil {
		writeError(w, http.StatusNotFound, "proposal not found")
		return
	}
	writeJSON(w, http.StatusOK, comment)
}

// POST /api/internal/comments/:id/deny
func (h *InternalHandler) DenyProposal(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")
	parts := strings.Split(path, "/")
	if len(parts) < 5 {
		writeError(w, http.StatusBadRequest, "invalid path")
		return
	}
	commentID := parts[4]

	var req model.UpdateProposalRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	comment, err := h.store.UpdateProposalStatusUnscoped(r.Context(), commentID, "DENIED", req.Feedback, time.Now().UnixMilli())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to deny proposal")
		return
	}
	if comment == nil {
		writeError(w, http.StatusNotFound, "proposal not found")
		return
	}
	writeJSON(w, http.StatusOK, comment)
}

// ─── WorkItems ──────────────────────────────────────────────────────────────
// See docs/WORK_ITEMS_DESIGN.md for the design and state machine.

// POST /api/internal/work-items
// Idempotent on triggering_comment_id: if a WorkItem already exists for the
// given comment, returns the existing one (HTTP 200) instead of creating a
// duplicate. New creations return HTTP 201.
func (h *InternalHandler) CreateWorkItem(w http.ResponseWriter, r *http.Request) {
	var req model.CreateWorkItemRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.TaskID == "" || req.TargetPersona == "" {
		writeError(w, http.StatusBadRequest, "taskId and targetPersona are required")
		return
	}

	now := time.Now().UnixMilli()
	maxRetries := 5
	if req.MaxRetries != nil {
		maxRetries = *req.MaxRetries
	}
	promptCtx := req.PromptContext
	if promptCtx == nil {
		promptCtx = json.RawMessage("{}")
	}
	props := req.Props
	if props == nil {
		props = json.RawMessage("{}")
	}

	wi := &model.WorkItem{
		ID:                  uuid.New().String(),
		TaskID:              req.TaskID,
		TriggeringCommentID: req.TriggeringCommentID,
		TargetPersona:       req.TargetPersona,
		PromptContext:       promptCtx,
		Output:              json.RawMessage("{}"),
		Status:              "pending",
		RetryCount:          0,
		MaxRetries:          maxRetries,
		Attempts:            json.RawMessage("[]"),
		CreatedAt:           now,
		UpdatedAt:           now,
		Props:               props,
	}

	result, created, err := h.store.CreateWorkItemIdempotent(r.Context(), wi)
	if err != nil {
		log.Printf("CreateWorkItem: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create work item")
		return
	}
	status := http.StatusOK
	if created {
		status = http.StatusCreated
	}
	writeJSON(w, status, result)
}

// GET /api/internal/work-items?task_id=&status=&persona=
func (h *InternalHandler) ListWorkItems(w http.ResponseWriter, r *http.Request) {
	var taskIDPtr, statusPtr, personaPtr *string
	if s := r.URL.Query().Get("task_id"); s != "" {
		taskIDPtr = &s
	}
	if s := r.URL.Query().Get("status"); s != "" {
		statusPtr = &s
	}
	if s := r.URL.Query().Get("persona"); s != "" {
		personaPtr = &s
	}

	items, err := h.store.ListWorkItems(r.Context(), taskIDPtr, statusPtr, personaPtr)
	if err != nil {
		log.Printf("ListWorkItems: %v", err)
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if items == nil {
		items = []model.WorkItem{}
	}
	writeJSON(w, http.StatusOK, items)
}

// GET /api/internal/work-items/pickup
// Returns WorkItems eligible for dispatch: pending OR (failed AND retry_count
// < max_retries). Used by work_item_handler poller.
func (h *InternalHandler) ListWorkItemsForPickup(w http.ResponseWriter, r *http.Request) {
	items, err := h.store.ListWorkItemsForPickup(r.Context())
	if err != nil {
		log.Printf("ListWorkItemsForPickup: %v", err)
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if items == nil {
		items = []model.WorkItem{}
	}
	writeJSON(w, http.StatusOK, items)
}

// GET /api/internal/work-items/{id}
func (h *InternalHandler) GetWorkItem(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
	wi, err := h.store.GetWorkItem(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if wi == nil {
		writeError(w, http.StatusNotFound, "work item not found")
		return
	}
	writeJSON(w, http.StatusOK, wi)
}

// PATCH /api/internal/work-items/{id}
// Partial update: status, retry_count, props. Status transitions validated.
func (h *InternalHandler) UpdateWorkItem(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
	var req model.UpdateWorkItemRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	wi, err := h.store.UpdateWorkItem(r.Context(), id, &req, time.Now().UnixMilli())
	if err != nil {
		// State machine violations come back as fmt.Errorf with a clear message.
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}
	if wi == nil {
		writeError(w, http.StatusNotFound, "work item not found")
		return
	}
	writeJSON(w, http.StatusOK, wi)
}

// POST /api/internal/work-items/{id}/submit-output
// Records the AI's parsed output and flips status to 'completed'.
// Only valid when current status is 'dispatched'.
func (h *InternalHandler) SubmitWorkItemOutput(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3) // /api/internal/work-items/:id/submit-output
	var req model.SubmitWorkItemOutputRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if len(req.Output) == 0 {
		writeError(w, http.StatusBadRequest, "output is required")
		return
	}
	wi, err := h.store.SubmitWorkItemOutput(r.Context(), id, req.Output, time.Now().UnixMilli())
	if err != nil {
		log.Printf("SubmitWorkItemOutput(%s): %v", id, err)
		writeError(w, http.StatusInternalServerError, "failed to submit output")
		return
	}
	if wi == nil {
		writeError(w, http.StatusNotFound, "work item not found or not in dispatched state")
		return
	}
	writeJSON(w, http.StatusOK, wi)
}

// POST /api/internal/work-items/{id}/record-attempt
// Appends an attempt entry, increments retry_count, flips to 'failed'.
// Only valid from 'dispatched'.
func (h *InternalHandler) RecordWorkItemAttempt(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
	var req model.RecordWorkItemAttemptRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Error == "" {
		writeError(w, http.StatusBadRequest, "error is required")
		return
	}
	now := time.Now().UnixMilli()
	attempt := map[string]any{
		"at":    now,
		"error": req.Error,
	}
	if req.DurationMs != nil {
		attempt["durationMs"] = *req.DurationMs
	}
	if req.CostUSD != nil {
		attempt["costUsd"] = *req.CostUSD
	}
	if req.Runtime != "" {
		attempt["runtime"] = req.Runtime
	}
	if req.Model != "" {
		attempt["model"] = req.Model
	}
	if req.StopReason != "" {
		attempt["stopReason"] = req.StopReason
	}
	attemptJSON, err := json.Marshal(attempt)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to encode attempt")
		return
	}
	wi, err := h.store.RecordWorkItemAttempt(r.Context(), id, attemptJSON, req.Error, now)
	if err != nil {
		log.Printf("RecordWorkItemAttempt(%s): %v", id, err)
		writeError(w, http.StatusInternalServerError, "failed to record attempt")
		return
	}
	if wi == nil {
		writeError(w, http.StatusNotFound, "work item not found or not in dispatched state")
		return
	}
	writeJSON(w, http.StatusOK, wi)
}

// ServeHTTP routes /api/internal/ requests.
func (h *InternalHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")

	switch {
	// POST /api/internal/tasks
	case r.Method == http.MethodPost && path == "/api/internal/tasks":
		h.CreateTask(w, r)

	// GET /api/internal/tasks
	// GET /api/internal/tasks/search?status=...&aiStatus=...&algorithm=...&aiEnabled=true
	case r.Method == http.MethodGet && path == "/api/internal/tasks/search":
		h.SearchTasks(w, r)

	case r.Method == http.MethodGet && path == "/api/internal/tasks":
		h.ListTasks(w, r)

	// GET /api/internal/comments?needs_ai_reply=true
	// Must come BEFORE the suffix-match for /comments, otherwise it routes
	// to ListComments (per-task) and produces a malformed query.
	case r.Method == http.MethodGet && path == "/api/internal/comments" && r.URL.Query().Get("needs_ai_reply") == "true":
		h.ListCommentsNeedingAIReply(w, r)

	// GET /api/internal/tasks/:id/children
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/children"):
		h.ListChildren(w, r)

	// GET /api/internal/tasks/:id/comments
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/comments"):
		h.ListComments(w, r)

	// POST /api/internal/tasks/:id/comments
	case r.Method == http.MethodPost && strings.HasSuffix(path, "/comments"):
		h.CreateComment(w, r)

	// GET /api/internal/tasks/:id
	case r.Method == http.MethodGet && strings.HasPrefix(path, "/api/internal/tasks/") && strings.Count(path, "/") == 4:
		h.GetTask(w, r)

	// PATCH /api/internal/tasks/:id
	case r.Method == http.MethodPatch && strings.HasPrefix(path, "/api/internal/tasks/") && strings.Count(path, "/") == 4:
		h.UpdateTask(w, r)

	// DELETE /api/internal/tasks/:id
	case r.Method == http.MethodDelete && strings.HasPrefix(path, "/api/internal/tasks/") && strings.Count(path, "/") == 4:
		h.DeleteTask(w, r)

	// POST /api/internal/comments/:id/approve
	case r.Method == http.MethodPost && strings.HasSuffix(path, "/approve"):
		h.ApproveProposal(w, r)

	// POST /api/internal/comments/:id/deny
	case r.Method == http.MethodPost && strings.HasSuffix(path, "/deny"):
		h.DenyProposal(w, r)

	// PATCH /api/internal/comments/:id
	case r.Method == http.MethodPatch && strings.HasPrefix(path, "/api/internal/comments/") && strings.Count(path, "/") == 4:
		h.UpdateComment(w, r)

	// ── WorkItems ────────────────────────────────────────────────────
	// /pickup must be checked before /:id, and the action subpaths
	// (/submit-output, /record-attempt) before plain /:id.

	// POST /api/internal/work-items
	case r.Method == http.MethodPost && path == "/api/internal/work-items":
		h.CreateWorkItem(w, r)

	// GET /api/internal/work-items/pickup  (poller queue scan)
	case r.Method == http.MethodGet && path == "/api/internal/work-items/pickup":
		h.ListWorkItemsForPickup(w, r)

	// GET /api/internal/work-items?…  (list/filter)
	case r.Method == http.MethodGet && path == "/api/internal/work-items":
		h.ListWorkItems(w, r)

	// POST /api/internal/work-items/:id/submit-output
	case r.Method == http.MethodPost && strings.HasPrefix(path, "/api/internal/work-items/") && strings.HasSuffix(path, "/submit-output"):
		h.SubmitWorkItemOutput(w, r)

	// POST /api/internal/work-items/:id/record-attempt
	case r.Method == http.MethodPost && strings.HasPrefix(path, "/api/internal/work-items/") && strings.HasSuffix(path, "/record-attempt"):
		h.RecordWorkItemAttempt(w, r)

	// GET /api/internal/work-items/:id
	case r.Method == http.MethodGet && strings.HasPrefix(path, "/api/internal/work-items/") && strings.Count(path, "/") == 4:
		h.GetWorkItem(w, r)

	// PATCH /api/internal/work-items/:id
	case r.Method == http.MethodPatch && strings.HasPrefix(path, "/api/internal/work-items/") && strings.Count(path, "/") == 4:
		h.UpdateWorkItem(w, r)

	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}
