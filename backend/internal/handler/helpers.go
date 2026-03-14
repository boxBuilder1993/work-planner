package handler

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/boxBuilder1993/work-planner/backend/internal/auth"
)

const maxBodySize = 1 << 20 // 1 MB

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func decodeJSON(r *http.Request, v any) error {
	r.Body = http.MaxBytesReader(nil, r.Body, maxBodySize)
	defer r.Body.Close()
	return json.NewDecoder(r.Body).Decode(v)
}

func getUserID(r *http.Request) string {
	uid, ok := r.Context().Value(auth.UserIDKey).(string)
	if !ok {
		return ""
	}
	return uid
}

// extractPathParam extracts a path segment by position from the URL.
// For example, extractPathParam("/api/tasks/abc-123", 2) returns "abc-123".
func extractPathParam(path string, index int) string {
	parts := strings.Split(strings.Trim(path, "/"), "/")
	if index < len(parts) {
		return parts[index]
	}
	return ""
}
