package handler

import (
	"errors"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
)

// PlannerHandler serves the user-facing (JWT) planner API used by the web.
// It reuses the same store methods as the internal API; the user is taken from
// the JWT context (getUserID) rather than an explicit user_id.
type PlannerHandler struct {
	store *store.Store
}

func NewPlannerHandler(s *store.Store) *PlannerHandler {
	return &PlannerHandler{store: s}
}

// ServeHTTP routes the planner public endpoints (registered in main.go under
// /api/people, /api/calendar, /api/holidays, /api/time-off, /api/dependencies,
// /api/schedule, and the /api/tasks/:id/{dependencies,planner} sub-routes).
func (h *PlannerHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimSuffix(r.URL.Path, "/")
	switch {
	// People + time off
	case r.Method == http.MethodPost && path == "/api/people":
		h.createPerson(w, r)
	case r.Method == http.MethodGet && path == "/api/people":
		h.listPeople(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(path, "/api/people/") && strings.HasSuffix(path, "/time-off"):
		h.listTimeOff(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(path, "/api/people/") && strings.HasSuffix(path, "/time-off"):
		h.createTimeOff(w, r)
	case r.Method == http.MethodPatch && strings.HasPrefix(path, "/api/people/") && strings.Count(path, "/") == 3:
		h.updatePerson(w, r)
	case r.Method == http.MethodDelete && strings.HasPrefix(path, "/api/people/") && strings.Count(path, "/") == 3:
		h.deletePerson(w, r)
	case r.Method == http.MethodDelete && strings.HasPrefix(path, "/api/time-off/"):
		h.deleteTimeOff(w, r)

	// Calendar + holidays
	case r.Method == http.MethodGet && path == "/api/calendar":
		h.getCalendar(w, r)
	case r.Method == http.MethodPut && path == "/api/calendar":
		h.upsertCalendar(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(path, "/api/calendar/") && strings.HasSuffix(path, "/holidays"):
		h.listHolidays(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(path, "/api/calendar/") && strings.HasSuffix(path, "/holidays"):
		h.createHoliday(w, r)
	case r.Method == http.MethodDelete && strings.HasPrefix(path, "/api/holidays/"):
		h.deleteHoliday(w, r)

	// Dependencies + planner fields + schedule
	case r.Method == http.MethodGet && strings.HasPrefix(path, "/api/tasks/") && strings.HasSuffix(path, "/dependencies"):
		h.listDependencies(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(path, "/api/tasks/") && strings.HasSuffix(path, "/dependencies"):
		h.createDependency(w, r)
	case r.Method == http.MethodDelete && strings.HasPrefix(path, "/api/dependencies/"):
		h.deleteDependency(w, r)
	case r.Method == http.MethodPatch && strings.HasPrefix(path, "/api/tasks/") && strings.HasSuffix(path, "/planner"):
		h.updateTaskPlanner(w, r)
	case r.Method == http.MethodGet && path == "/api/schedule":
		h.getSchedule(w, r)

	default:
		writeError(w, http.StatusNotFound, "not found")
	}
}

// ─── People ──────────────────────────────────────────────────────────────────

func (h *PlannerHandler) createPerson(w http.ResponseWriter, r *http.Request) {
	var req model.CreatePersonRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Name == "" {
		writeError(w, http.StatusBadRequest, "name is required")
		return
	}
	hpd := 8.0
	if req.HoursPerDay != nil {
		hpd = *req.HoursPerDay
	}
	p, err := h.store.CreatePerson(r.Context(), getUserID(r), req.Name, req.Email, hpd)
	if err != nil {
		log.Printf("createPerson: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create person")
		return
	}
	writeJSON(w, http.StatusCreated, p)
}

func (h *PlannerHandler) listPeople(w http.ResponseWriter, r *http.Request) {
	people, err := h.store.ListPeople(r.Context(), getUserID(r))
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, people)
}

func (h *PlannerHandler) updatePerson(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 2)
	var req model.UpdatePersonRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	p, err := h.store.UpdatePerson(r.Context(), id, &req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to update person")
		return
	}
	if p == nil {
		writeError(w, http.StatusNotFound, "person not found")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

func (h *PlannerHandler) deletePerson(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 2)
	ok, err := h.store.DeletePerson(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete person")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "person not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": id})
}

func (h *PlannerHandler) createTimeOff(w http.ResponseWriter, r *http.Request) {
	personID := extractPathParam(r.URL.Path, 2)
	var req model.CreateTimeOffRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.StartDay == "" || req.EndDay == "" {
		writeError(w, http.StatusBadRequest, "startDay and endDay are required")
		return
	}
	t, err := h.store.CreateTimeOff(r.Context(), personID, &req)
	if err != nil {
		log.Printf("createTimeOff: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create time off")
		return
	}
	writeJSON(w, http.StatusCreated, t)
}

func (h *PlannerHandler) listTimeOff(w http.ResponseWriter, r *http.Request) {
	personID := extractPathParam(r.URL.Path, 2)
	off, err := h.store.ListTimeOff(r.Context(), personID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, off)
}

func (h *PlannerHandler) deleteTimeOff(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 2)
	ok, err := h.store.DeleteTimeOff(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete time off")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "time off not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": id})
}

// ─── Calendar + holidays ─────────────────────────────────────────────────────

func (h *PlannerHandler) getCalendar(w http.ResponseWriter, r *http.Request) {
	c, err := h.store.GetOrCreateCalendar(r.Context(), getUserID(r))
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, c)
}

func (h *PlannerHandler) upsertCalendar(w http.ResponseWriter, r *http.Request) {
	var req model.UpsertCalendarRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	userID := getUserID(r)
	c, err := h.store.GetOrCreateCalendar(r.Context(), userID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	wd := c.WeekendDays
	if req.WeekendDays != nil {
		wd = *req.WeekendDays
	}
	c, err = h.store.UpsertCalendar(r.Context(), userID, wd)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to update calendar")
		return
	}
	writeJSON(w, http.StatusOK, c)
}

func (h *PlannerHandler) createHoliday(w http.ResponseWriter, r *http.Request) {
	calendarID := extractPathParam(r.URL.Path, 2)
	var req model.CreateHolidayRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.Day == "" {
		writeError(w, http.StatusBadRequest, "day is required")
		return
	}
	hh, err := h.store.CreateHoliday(r.Context(), calendarID, req.Day, req.Name)
	if err != nil {
		log.Printf("createHoliday: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create holiday")
		return
	}
	writeJSON(w, http.StatusCreated, hh)
}

func (h *PlannerHandler) listHolidays(w http.ResponseWriter, r *http.Request) {
	calendarID := extractPathParam(r.URL.Path, 2)
	hs, err := h.store.ListHolidays(r.Context(), calendarID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, hs)
}

func (h *PlannerHandler) deleteHoliday(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 2)
	ok, err := h.store.DeleteHoliday(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete holiday")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "holiday not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": id})
}

// ─── Dependencies + planner fields + schedule ────────────────────────────────

func (h *PlannerHandler) createDependency(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	var req model.CreateDependencyRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.DependsOnID == "" {
		writeError(w, http.StatusBadRequest, "dependsOnId is required")
		return
	}
	d, err := h.store.CreateDependency(r.Context(), taskID, req.DependsOnID)
	if errors.Is(err, store.ErrDependencyCycle) {
		writeError(w, http.StatusConflict, "dependency would create a cycle")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to create dependency")
		return
	}
	writeJSON(w, http.StatusCreated, d)
}

func (h *PlannerHandler) listDependencies(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	deps, err := h.store.ListDependencies(r.Context(), taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, deps)
}

func (h *PlannerHandler) deleteDependency(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 2)
	ok, err := h.store.DeleteDependency(r.Context(), id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to delete dependency")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "dependency not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": id})
}

func (h *PlannerHandler) updateTaskPlanner(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 2)
	var req model.UpdateTaskPlannerRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	ok, err := h.store.UpdateTaskPlanner(r.Context(), taskID, &req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to update task planner fields")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": taskID})
}

func (h *PlannerHandler) getSchedule(w http.ResponseWriter, r *http.Request) {
	start := r.URL.Query().Get("start")
	if start == "" {
		start = time.Now().UTC().Format("2006-01-02")
	}
	rows, err := h.store.ComputeSchedule(r.Context(), getUserID(r), start)
	if err != nil {
		log.Printf("getSchedule: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to compute schedule")
		return
	}
	writeJSON(w, http.StatusOK, rows)
}
