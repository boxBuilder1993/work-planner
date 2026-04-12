package handler

import (
	"log"
	"net/http"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/auth"
	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/google/uuid"
)

type AuthHandler struct {
	auth  *auth.Auth
	store *store.Store
}

func NewAuthHandler(a *auth.Auth, s *store.Store) *AuthHandler {
	return &AuthHandler{auth: a, store: s}
}

func (h *AuthHandler) HandleLocalAuth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var req model.AuthLocalRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Email == "" {
		writeError(w, http.StatusBadRequest, "email is required")
		return
	}
	if req.Name == "" {
		req.Name = req.Email
	}

	user, err := h.store.GetUserByEmail(r.Context(), req.Email)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if user == nil {
		user = &model.User{
			ID:        uuid.New().String(),
			Email:     req.Email,
			Name:      req.Name,
			CreatedAt: time.Now().UnixMilli(),
		}
	} else {
		user.Name = req.Name
	}

	if err := h.store.UpsertUser(r.Context(), user); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to save user")
		return
	}

	token, err := h.auth.GenerateJWT(user.ID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to generate token")
		return
	}

	writeJSON(w, http.StatusOK, model.AuthResponse{Token: token, User: *user})
}

func (h *AuthHandler) HandleGoogleAuth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var req model.AuthGoogleRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.IDToken == "" {
		writeError(w, http.StatusBadRequest, "idToken is required")
		return
	}

	claims, err := h.auth.ValidateGoogleToken(r.Context(), req.IDToken)
	if err != nil {
		log.Printf("Google token validation failed: %v", err)
		writeError(w, http.StatusUnauthorized, "invalid google token")
		return
	}

	// Check if user exists.
	user, err := h.store.GetUserByEmail(r.Context(), claims.Email)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}

	if user == nil {
		user = &model.User{
			ID:        uuid.New().String(),
			Email:     claims.Email,
			Name:      claims.Name,
			CreatedAt: time.Now().UnixMilli(),
		}
	} else {
		user.Name = claims.Name
	}

	if req.RefreshToken != "" {
		user.GoogleRefreshToken = &req.RefreshToken
	}

	if err := h.store.UpsertUser(r.Context(), user); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to save user")
		return
	}

	token, err := h.auth.GenerateJWT(user.ID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to generate token")
		return
	}

	writeJSON(w, http.StatusOK, model.AuthResponse{Token: token, User: *user})
}
