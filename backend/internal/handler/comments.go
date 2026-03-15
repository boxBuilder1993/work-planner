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

type CommentHandler struct {
	store *store.Store
}

func NewCommentHandler(s *store.Store) *CommentHandler {
	return &CommentHandler{store: s}
}

// GET /api/tasks/:id/comments?type=PROPOSAL
func (h *CommentHandler) List(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2) // /api/tasks/:id/comments
	userID := getUserID(r)

	var commentType *string
	if ct := r.URL.Query().Get("type"); ct != "" {
		commentType = &ct
	}

	comments, err := h.store.ListComments(r.Context(), userID, taskID, commentType)
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
		CreatedAt:       now,
		UpdatedAt:       now,
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

// POST /api/comments/:id/approve
func (h *CommentHandler) Approve(w http.ResponseWriter, r *http.Request) {
	commentID := extractPathParam(r.URL.Path, 2) // /api/comments/:id/approve
	userID := getUserID(r)

	comment, err := h.store.UpdateProposalStatus(r.Context(), userID, commentID, "APPROVED", nil, time.Now().UnixMilli())
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

// POST /api/comments/:id/deny
func (h *CommentHandler) Deny(w http.ResponseWriter, r *http.Request) {
	commentID := extractPathParam(r.URL.Path, 2) // /api/comments/:id/deny
	userID := getUserID(r)

	var req model.UpdateProposalRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	comment, err := h.store.UpdateProposalStatus(r.Context(), userID, commentID, "DENIED", req.Feedback, time.Now().UnixMilli())
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

// ServeDeleteHTTP routes /api/comments/:id and /api/comments/:id/approve|deny requests.
func (h *CommentHandler) ServeDeleteHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")

	switch {
	case r.Method == http.MethodDelete && strings.Count(path, "/") == 3:
		h.Delete(w, r)
	case r.Method == http.MethodPost && strings.HasSuffix(path, "/approve"):
		h.Approve(w, r)
	case r.Method == http.MethodPost && strings.HasSuffix(path, "/deny"):
		h.Deny(w, r)
	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}
