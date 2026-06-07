package handler

import (
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/jackc/pgx/v5"
)

// KnowledgeHandler serves the user-facing (JWT) /api/knowledge-cards endpoints
// that back the web Knowledge Cards page. Cards are global/company-wide — there
// is no per-user scoping — so this mirrors the internal-key handlers in
// internal.go, just at the shorter route prefix (the id sits one path segment
// earlier).
type KnowledgeHandler struct {
	store *store.Store
}

func NewKnowledgeHandler(s *store.Store) *KnowledgeHandler {
	return &KnowledgeHandler{store: s}
}

func (h *KnowledgeHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := r.URL.Path
	switch {
	case r.Method == http.MethodGet && path == "/api/knowledge-cards/search":
		h.Search(w, r)
	case r.Method == http.MethodGet && path == "/api/knowledge-cards":
		h.List(w, r)
	case r.Method == http.MethodPost && path == "/api/knowledge-cards":
		h.Create(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(path, "/api/knowledge-cards/"):
		h.Get(w, r)
	case r.Method == http.MethodPatch && strings.HasPrefix(path, "/api/knowledge-cards/"):
		h.Update(w, r)
	case r.Method == http.MethodDelete && strings.HasPrefix(path, "/api/knowledge-cards/"):
		h.Delete(w, r)
	default:
		writeError(w, http.StatusNotFound, "not found")
	}
}

// id is at segment 2: /api/knowledge-cards/:id
func (h *KnowledgeHandler) cardID(path string) string { return extractPathParam(path, 2) }

func (h *KnowledgeHandler) List(w http.ResponseWriter, r *http.Request) {
	var tagPtr *string
	if t := r.URL.Query().Get("tag"); t != "" {
		tagPtr = &t
	}
	includeInvalid := r.URL.Query().Get("includeInvalid") == "true"
	cards, err := h.store.ListKnowledgeCards(r.Context(), tagPtr, includeInvalid)
	if err != nil {
		log.Printf("List cards: %v", err)
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if cards == nil {
		cards = []model.KnowledgeCard{}
	}
	writeJSON(w, http.StatusOK, cards)
}

func (h *KnowledgeHandler) Search(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	var tagPtr *string
	if t := r.URL.Query().Get("tag"); t != "" {
		tagPtr = &t
	}
	includeInvalid := r.URL.Query().Get("includeInvalid") == "true"
	limit := 50
	if l := r.URL.Query().Get("limit"); l != "" {
		if n, err := strconv.Atoi(l); err == nil && n > 0 {
			limit = n
		}
	}
	cards, err := h.store.SearchKnowledgeCards(r.Context(), q, tagPtr, includeInvalid, limit)
	if err != nil {
		log.Printf("Search cards: %v", err)
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if cards == nil {
		cards = []model.KnowledgeCard{}
	}
	writeJSON(w, http.StatusOK, cards)
}

func (h *KnowledgeHandler) Get(w http.ResponseWriter, r *http.Request) {
	card, err := h.store.GetKnowledgeCard(r.Context(), h.cardID(r.URL.Path))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if card == nil {
		writeError(w, http.StatusNotFound, "card not found")
		return
	}
	writeJSON(w, http.StatusOK, card)
}

func (h *KnowledgeHandler) Create(w http.ResponseWriter, r *http.Request) {
	var req model.CreateKnowledgeCardRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if !validCardSlug.MatchString(req.ID) {
		writeError(w, http.StatusBadRequest, "id must be a slug: lowercase letters, digits, hyphens (2-64 chars)")
		return
	}
	if strings.TrimSpace(req.Content) == "" {
		writeError(w, http.StatusBadRequest, "content is required")
		return
	}
	now := time.Now().UnixMilli()
	tags := req.Tags
	if tags == nil {
		tags = []string{}
	}
	card := &model.KnowledgeCard{
		ID: req.ID, Content: req.Content, Tags: tags, IsValid: true,
		CreatedAt: now, UpdatedAt: now,
	}
	if err := h.store.CreateKnowledgeCard(r.Context(), card); err != nil {
		if strings.Contains(err.Error(), "23505") || strings.Contains(strings.ToLower(err.Error()), "duplicate") {
			writeError(w, http.StatusConflict, "a card with that id already exists")
			return
		}
		log.Printf("Create card: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create card")
		return
	}
	writeJSON(w, http.StatusCreated, card)
}

func (h *KnowledgeHandler) Update(w http.ResponseWriter, r *http.Request) {
	var req model.UpdateKnowledgeCardRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	card, err := h.store.UpdateKnowledgeCard(r.Context(), h.cardID(r.URL.Path), &req, time.Now().UnixMilli())
	if err != nil {
		log.Printf("Update card: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to update card")
		return
	}
	if card == nil {
		writeError(w, http.StatusNotFound, "card not found")
		return
	}
	writeJSON(w, http.StatusOK, card)
}

func (h *KnowledgeHandler) Delete(w http.ResponseWriter, r *http.Request) {
	id := h.cardID(r.URL.Path)
	err := h.store.DeleteKnowledgeCard(r.Context(), id)
	if err == pgx.ErrNoRows {
		writeError(w, http.StatusNotFound, "card not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete card")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": id})
}
