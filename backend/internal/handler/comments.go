package handler

import (
	"net/http"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

type CommentHandler struct {
	store *store.Store
}

func NewCommentHandler(s *store.Store) *CommentHandler {
	return &CommentHandler{store: s}
}

// GET /api/tasks/:id/comments
func (h *CommentHandler) List(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2) // /api/tasks/:id/comments
	userID := getUserID(r)

	comments, err := h.store.ListComments(r.Context(), userID, taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if comments == nil {
		comments = []model.Comment{}
	}

	writeJSON(w, http.StatusOK, comments)
}

// POST /api/tasks/:id/comments
func (h *CommentHandler) Create(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	userID := getUserID(r)

	var req model.CreateCommentRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Text == "" {
		writeError(w, http.StatusBadRequest, "text is required")
		return
	}

	now := time.Now().UnixMilli()
	comment := &model.Comment{
		ID:        uuid.New().String(),
		TaskID:    taskID,
		Text:      req.Text,
		CreatedAt: now,
		UpdatedAt: now,
	}

	err := h.store.CreateComment(r.Context(), userID, comment)
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

// DELETE /api/comments/:id
func (h *CommentHandler) Delete(w http.ResponseWriter, r *http.Request) {
	commentID := extractPathParam(r.URL.Path, 2) // /api/comments/:id
	userID := getUserID(r)

	err := h.store.DeleteComment(r.Context(), userID, commentID)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "comment not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete comment")
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// ServeHTTP routes /api/tasks/:id/comments requests.
func (h *CommentHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.List(w, r)
	case http.MethodPost:
		h.Create(w, r)
	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}

// ServeDeleteHTTP routes /api/comments/:id requests.
func (h *CommentHandler) ServeDeleteHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	h.Delete(w, r)
}
