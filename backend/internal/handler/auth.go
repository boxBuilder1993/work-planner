package handler

import (
	"log"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/auth"
	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
)

const minPasswordLen = 8

func normalizeEmail(e string) string { return strings.ToLower(strings.TrimSpace(e)) }

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

// issueToken generates a JWT for the user and writes the standard auth response.
func (h *AuthHandler) issueToken(w http.ResponseWriter, user *model.User) {
	token, err := h.auth.GenerateJWT(user.ID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to generate token")
		return
	}
	writeJSON(w, http.StatusOK, model.AuthResponse{Token: token, User: *user})
}

// HandleRegister creates a new email+password account.
func (h *AuthHandler) HandleRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	var req model.AuthRegisterRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	email := normalizeEmail(req.Email)
	if email == "" || !strings.Contains(email, "@") {
		writeError(w, http.StatusBadRequest, "a valid email is required")
		return
	}
	if len(req.Password) < minPasswordLen {
		writeError(w, http.StatusBadRequest, "password must be at least 8 characters")
		return
	}
	existing, err := h.store.GetUserByEmail(r.Context(), email)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	if existing != nil {
		writeError(w, http.StatusConflict, "an account with this email already exists")
		return
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to hash password")
		return
	}
	name := strings.TrimSpace(req.Name)
	if name == "" {
		name = email
	}
	hs := string(hash)
	user := &model.User{ID: uuid.New().String(), Email: email, Name: name, PasswordHash: &hs, CreatedAt: time.Now().UnixMilli()}
	if err := h.store.UpsertUser(r.Context(), user); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to save user")
		return
	}
	h.issueToken(w, user)
}

// HandleLogin verifies an email+password and returns a JWT.
func (h *AuthHandler) HandleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	if !loginLimiter.allow(clientIP(r)) {
		writeError(w, http.StatusTooManyRequests, "too many attempts; please wait a moment")
		return
	}
	var req model.AuthLoginRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	user, err := h.store.GetUserByEmail(r.Context(), normalizeEmail(req.Email))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "database error")
		return
	}
	// Generic failure — don't reveal whether the email exists or has a password.
	if user == nil || user.PasswordHash == nil ||
		bcrypt.CompareHashAndPassword([]byte(*user.PasswordHash), []byte(req.Password)) != nil {
		writeError(w, http.StatusUnauthorized, "invalid email or password")
		return
	}
	h.issueToken(w, user)
}

// HandleSetPassword sets/changes the current (authenticated) user's password.
func (h *AuthHandler) HandleSetPassword(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	userID := getUserID(r)
	if userID == "" {
		writeError(w, http.StatusUnauthorized, "unauthorized")
		return
	}
	var req model.SetPasswordRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if len(req.Password) < minPasswordLen {
		writeError(w, http.StatusBadRequest, "password must be at least 8 characters")
		return
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to hash password")
		return
	}
	if err := h.store.SetUserPassword(r.Context(), userID, string(hash)); err != nil {
		writeError(w, http.StatusInternalServerError, "failed to set password")
		return
	}
	writeJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

// ─── Login rate limiting (in-memory, per-IP sliding window) ──────────────────

type rateLimiter struct {
	mu     sync.Mutex
	hits   map[string][]time.Time
	max    int
	window time.Duration
}

func newRateLimiter(max int, window time.Duration) *rateLimiter {
	return &rateLimiter{hits: map[string][]time.Time{}, max: max, window: window}
}

func (l *rateLimiter) allow(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	cutoff := time.Now().Add(-l.window)
	kept := l.hits[key][:0]
	for _, t := range l.hits[key] {
		if t.After(cutoff) {
			kept = append(kept, t)
		}
	}
	if len(kept) >= l.max {
		l.hits[key] = kept
		return false
	}
	l.hits[key] = append(kept, time.Now())
	return true
}

var loginLimiter = newRateLimiter(10, time.Minute)

func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		if i := strings.IndexByte(xff, ','); i >= 0 {
			return strings.TrimSpace(xff[:i])
		}
		return strings.TrimSpace(xff)
	}
	if host, _, err := net.SplitHostPort(r.RemoteAddr); err == nil {
		return host
	}
	return r.RemoteAddr
}
