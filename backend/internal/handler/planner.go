package handler

import (
	"errors"
	"log"
	"net/http"
	"time"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/store"
)

// Planner internal API: people, time off, the shared calendar + holidays, and
// task dependencies. User-scoping is by explicit user_id (internal key auth),
// mirroring the task endpoints. See docs/PLANNER_IMPLEMENTATION.md.

const errDBPlanner = "database error"

// ─── People ──────────────────────────────────────────────────────────────────

func (h *InternalHandler) CreatePerson(w http.ResponseWriter, r *http.Request) {
	var req model.CreatePersonRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.UserID == "" || req.Name == "" {
		writeError(w, http.StatusBadRequest, "userId and name are required")
		return
	}
	hpd := 8.0
	if req.HoursPerDay != nil {
		hpd = *req.HoursPerDay
	}
	p, err := h.store.CreatePerson(r.Context(), req.UserID, req.Name, req.Email, hpd)
	if err != nil {
		log.Printf("CreatePerson: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create person")
		return
	}
	writeJSON(w, http.StatusCreated, p)
}

func (h *InternalHandler) ListPeople(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	if userID == "" {
		writeError(w, http.StatusBadRequest, "user_id is required")
		return
	}
	people, err := h.store.ListPeople(r.Context(), userID)
	if err != nil {
		log.Printf("ListPeople: %v", err)
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, people)
}

func (h *InternalHandler) UpdatePerson(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
	var req model.UpdatePersonRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	p, err := h.store.UpdatePerson(r.Context(), id, &req)
	if err != nil {
		log.Printf("UpdatePerson: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to update person")
		return
	}
	if p == nil {
		writeError(w, http.StatusNotFound, "person not found")
		return
	}
	writeJSON(w, http.StatusOK, p)
}

func (h *InternalHandler) DeletePerson(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
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

// ─── Time off ────────────────────────────────────────────────────────────────

func (h *InternalHandler) CreateTimeOff(w http.ResponseWriter, r *http.Request) {
	personID := extractPathParam(r.URL.Path, 3)
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
		log.Printf("CreateTimeOff: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create time off")
		return
	}
	writeJSON(w, http.StatusCreated, t)
}

func (h *InternalHandler) ListTimeOff(w http.ResponseWriter, r *http.Request) {
	personID := extractPathParam(r.URL.Path, 3)
	off, err := h.store.ListTimeOff(r.Context(), personID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, off)
}

func (h *InternalHandler) DeleteTimeOff(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
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

func (h *InternalHandler) GetCalendar(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	if userID == "" {
		writeError(w, http.StatusBadRequest, "user_id is required")
		return
	}
	c, err := h.store.GetOrCreateCalendar(r.Context(), userID)
	if err != nil {
		log.Printf("GetCalendar: %v", err)
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, c)
}

func (h *InternalHandler) UpsertCalendar(w http.ResponseWriter, r *http.Request) {
	var req model.UpsertCalendarRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	if req.UserID == "" {
		writeError(w, http.StatusBadRequest, "userId is required")
		return
	}
	c, err := h.store.GetOrCreateCalendar(r.Context(), req.UserID)
	if err != nil {
		log.Printf("UpsertCalendar(get): %v", err)
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	wd := c.WeekendDays
	if req.WeekendDays != nil {
		wd = *req.WeekendDays
	}
	c, err = h.store.UpsertCalendar(r.Context(), req.UserID, wd)
	if err != nil {
		log.Printf("UpsertCalendar: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to update calendar")
		return
	}
	writeJSON(w, http.StatusOK, c)
}

func (h *InternalHandler) CreateHoliday(w http.ResponseWriter, r *http.Request) {
	calendarID := extractPathParam(r.URL.Path, 3)
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
		log.Printf("CreateHoliday: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create holiday")
		return
	}
	writeJSON(w, http.StatusCreated, hh)
}

func (h *InternalHandler) ListHolidays(w http.ResponseWriter, r *http.Request) {
	calendarID := extractPathParam(r.URL.Path, 3)
	hs, err := h.store.ListHolidays(r.Context(), calendarID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, hs)
}

func (h *InternalHandler) DeleteHoliday(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
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

// ─── Dependencies ────────────────────────────────────────────────────────────

func (h *InternalHandler) CreateDependency(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3)
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
		log.Printf("CreateDependency: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to create dependency")
		return
	}
	writeJSON(w, http.StatusCreated, d)
}

func (h *InternalHandler) ListDependencies(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3)
	deps, err := h.store.ListDependencies(r.Context(), taskID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, errDBPlanner)
		return
	}
	writeJSON(w, http.StatusOK, deps)
}

func (h *InternalHandler) DeleteDependency(w http.ResponseWriter, r *http.Request) {
	id := extractPathParam(r.URL.Path, 3)
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

// ─── Task planner fields + schedule ──────────────────────────────────────────

func (h *InternalHandler) UpdateTaskPlanner(w http.ResponseWriter, r *http.Request) {
	taskID := extractPathParam(r.URL.Path, 3)
	var req model.UpdateTaskPlannerRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid request body")
		return
	}
	ok, err := h.store.UpdateTaskPlanner(r.Context(), taskID, &req)
	if err != nil {
		log.Printf("UpdateTaskPlanner: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to update task planner fields")
		return
	}
	if !ok {
		writeError(w, http.StatusNotFound, "task not found")
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": taskID})
}

// GetSchedule recomputes the workspace schedule and returns enriched rows.
// ?user_id=required &start=YYYY-MM-DD (defaults to today).
func (h *InternalHandler) GetSchedule(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	if userID == "" {
		writeError(w, http.StatusBadRequest, "user_id is required")
		return
	}
	start := r.URL.Query().Get("start")
	if start == "" {
		start = plannerToday()
	}
	rows, err := h.store.ComputeSchedule(r.Context(), userID, start)
	if err != nil {
		log.Printf("GetSchedule: %v", err)
		writeError(w, http.StatusInternalServerError, "failed to compute schedule")
		return
	}
	writeJSON(w, http.StatusOK, rows)
}

func plannerToday() string {
	return time.Now().UTC().Format("2006-01-02")
}
