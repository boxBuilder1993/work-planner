package store

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/boxBuilder1993/work-planner/backend/internal/model"
	"github.com/boxBuilder1993/work-planner/backend/internal/planner"
)

// ErrDependencyCycle is returned when adding a dependency would create a cycle.
var ErrDependencyCycle = errors.New("dependency would create a cycle")

// ErrReparentCycle is returned when re-parenting would make a task its own ancestor.
var ErrReparentCycle = errors.New("re-parent would create a cycle")

// ─── Calendar ────────────────────────────────────────────────────────────────

// GetOrCreateCalendar returns the workspace's single shared calendar, creating
// a default one (weekends = Sat+Sun) on first access.
func (s *Store) GetOrCreateCalendar(ctx context.Context, userID string) (*model.Calendar, error) {
	var c model.Calendar
	err := s.pool.QueryRow(ctx, `
		SELECT id, user_id, weekend_days, created_at, updated_at
		FROM calendar WHERE user_id = $1
	`, userID).Scan(&c.ID, &c.UserID, &c.WeekendDays, &c.CreatedAt, &c.UpdatedAt)
	if err == nil {
		return &c, nil
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}
	now := time.Now().UnixMilli()
	c = model.Calendar{ID: uuid.New().String(), UserID: userID, WeekendDays: 96, CreatedAt: now, UpdatedAt: now}
	_, err = s.pool.Exec(ctx, `
		INSERT INTO calendar (id, user_id, weekend_days, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5)
	`, c.ID, c.UserID, c.WeekendDays, c.CreatedAt, c.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &c, nil
}

// UpsertCalendar sets the weekend definition (creating the calendar if needed).
func (s *Store) UpsertCalendar(ctx context.Context, userID string, weekendDays int) (*model.Calendar, error) {
	c, err := s.GetOrCreateCalendar(ctx, userID)
	if err != nil {
		return nil, err
	}
	now := time.Now().UnixMilli()
	_, err = s.pool.Exec(ctx, `UPDATE calendar SET weekend_days = $1, updated_at = $2 WHERE id = $3`,
		weekendDays, now, c.ID)
	if err != nil {
		return nil, err
	}
	c.WeekendDays = weekendDays
	c.UpdatedAt = now
	return c, nil
}

func (s *Store) CreateHoliday(ctx context.Context, calendarID, day string, name *string) (*model.CompanyHoliday, error) {
	h := model.CompanyHoliday{ID: uuid.New().String(), CalendarID: calendarID, Day: day, Name: name, CreatedAt: time.Now().UnixMilli()}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO company_holidays (id, calendar_id, day, name, created_at)
		VALUES ($1, $2, $3::date, $4, $5)
	`, h.ID, h.CalendarID, h.Day, h.Name, h.CreatedAt)
	if err != nil {
		return nil, err
	}
	return &h, nil
}

func (s *Store) ListHolidays(ctx context.Context, calendarID string) ([]model.CompanyHoliday, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, calendar_id, day::text, name, created_at
		FROM company_holidays WHERE calendar_id = $1 ORDER BY day
	`, calendarID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.CompanyHoliday{}
	for rows.Next() {
		var h model.CompanyHoliday
		if err := rows.Scan(&h.ID, &h.CalendarID, &h.Day, &h.Name, &h.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, h)
	}
	return out, rows.Err()
}

func (s *Store) DeleteHoliday(ctx context.Context, id string) (bool, error) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM company_holidays WHERE id = $1`, id)
	return tag.RowsAffected() > 0, err
}

// ─── People ──────────────────────────────────────────────────────────────────

func (s *Store) CreatePerson(ctx context.Context, userID, name string, email *string, hoursPerDay float64) (*model.Person, error) {
	now := time.Now().UnixMilli()
	p := model.Person{
		ID: uuid.New().String(), UserID: userID, Name: name, Email: email,
		HoursPerDay: hoursPerDay, Active: true, CreatedAt: now, UpdatedAt: now,
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO people (id, user_id, name, email, hours_per_day, active, created_at, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
	`, p.ID, p.UserID, p.Name, p.Email, p.HoursPerDay, p.Active, p.CreatedAt, p.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &p, nil
}

func (s *Store) ListPeople(ctx context.Context, userID string) ([]model.Person, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, user_id, name, email, hours_per_day, active, created_at, updated_at
		FROM people WHERE user_id = $1 ORDER BY name
	`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.Person{}
	for rows.Next() {
		var p model.Person
		if err := rows.Scan(&p.ID, &p.UserID, &p.Name, &p.Email, &p.HoursPerDay, &p.Active, &p.CreatedAt, &p.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}

func (s *Store) UpdatePerson(ctx context.Context, id string, req *model.UpdatePersonRequest) (*model.Person, error) {
	now := time.Now().UnixMilli()
	var p model.Person
	err := s.pool.QueryRow(ctx, `
		UPDATE people SET
			name          = COALESCE($1, name),
			email         = COALESCE($2, email),
			hours_per_day = COALESCE($3, hours_per_day),
			active        = COALESCE($4, active),
			updated_at    = $5
		WHERE id = $6
		RETURNING id, user_id, name, email, hours_per_day, active, created_at, updated_at
	`, req.Name, req.Email, req.HoursPerDay, req.Active, now, id).Scan(
		&p.ID, &p.UserID, &p.Name, &p.Email, &p.HoursPerDay, &p.Active, &p.CreatedAt, &p.UpdatedAt)
	if err == pgx.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &p, nil
}

func (s *Store) DeletePerson(ctx context.Context, id string) (bool, error) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM people WHERE id = $1`, id)
	return tag.RowsAffected() > 0, err
}

// ─── Time off ────────────────────────────────────────────────────────────────

func (s *Store) CreateTimeOff(ctx context.Context, personID string, req *model.CreateTimeOffRequest) (*model.TimeOff, error) {
	now := time.Now().UnixMilli()
	t := model.TimeOff{
		ID: uuid.New().String(), PersonID: personID, StartDay: req.StartDay, EndDay: req.EndDay,
		HoursOff: req.HoursOff, Note: req.Note, CreatedAt: now, UpdatedAt: now,
	}
	_, err := s.pool.Exec(ctx, `
		INSERT INTO person_time_off (id, person_id, start_day, end_day, hours_off, note, created_at, updated_at)
		VALUES ($1, $2, $3::date, $4::date, $5, $6, $7, $8)
	`, t.ID, t.PersonID, t.StartDay, t.EndDay, t.HoursOff, t.Note, t.CreatedAt, t.UpdatedAt)
	if err != nil {
		return nil, err
	}
	return &t, nil
}

func (s *Store) ListTimeOff(ctx context.Context, personID string) ([]model.TimeOff, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, person_id, start_day::text, end_day::text, hours_off, note, created_at, updated_at
		FROM person_time_off WHERE person_id = $1 ORDER BY start_day
	`, personID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.TimeOff{}
	for rows.Next() {
		var t model.TimeOff
		if err := rows.Scan(&t.ID, &t.PersonID, &t.StartDay, &t.EndDay, &t.HoursOff, &t.Note, &t.CreatedAt, &t.UpdatedAt); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

func (s *Store) DeleteTimeOff(ctx context.Context, id string) (bool, error) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM person_time_off WHERE id = $1`, id)
	return tag.RowsAffected() > 0, err
}

// ─── Dependencies ────────────────────────────────────────────────────────────

// CreateDependency records that taskID is blocked by dependsOnID. Rejects
// self-edges and any edge that would introduce a cycle. Returns
// ErrDependencyCycle on a would-be cycle.
func (s *Store) CreateDependency(ctx context.Context, taskID, dependsOnID string) (*model.TaskDependency, error) {
	if taskID == dependsOnID {
		return nil, ErrDependencyCycle
	}
	// Cycle check: does dependsOnID already (transitively) depend on taskID?
	var hit int
	err := s.pool.QueryRow(ctx, `
		WITH RECURSIVE deps(id) AS (
			SELECT depends_on_id FROM task_dependencies WHERE task_id = $1
			UNION
			SELECT td.depends_on_id FROM task_dependencies td JOIN deps ON td.task_id = deps.id
		)
		SELECT 1 FROM deps WHERE id = $2 LIMIT 1
	`, dependsOnID, taskID).Scan(&hit)
	if err == nil {
		return nil, ErrDependencyCycle
	}
	if err != pgx.ErrNoRows {
		return nil, err
	}
	d := model.TaskDependency{ID: uuid.New().String(), TaskID: taskID, DependsOnID: dependsOnID, CreatedAt: time.Now().UnixMilli()}
	_, err = s.pool.Exec(ctx, `
		INSERT INTO task_dependencies (id, task_id, depends_on_id, created_at)
		VALUES ($1, $2, $3, $4)
	`, d.ID, d.TaskID, d.DependsOnID, d.CreatedAt)
	if err != nil {
		return nil, err
	}
	return &d, nil
}

func (s *Store) ListDependencies(ctx context.Context, taskID string) ([]model.TaskDependency, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, task_id, depends_on_id, created_at
		FROM task_dependencies WHERE task_id = $1 ORDER BY created_at
	`, taskID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []model.TaskDependency{}
	for rows.Next() {
		var d model.TaskDependency
		if err := rows.Scan(&d.ID, &d.TaskID, &d.DependsOnID, &d.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, d)
	}
	return out, rows.Err()
}

func (s *Store) DeleteDependency(ctx context.Context, id string) (bool, error) {
	tag, err := s.pool.Exec(ctx, `DELETE FROM task_dependencies WHERE id = $1`, id)
	return tag.RowsAffected() > 0, err
}

// ─── Task planner fields ─────────────────────────────────────────────────────

// UpdateTaskPlanner sets assignee_id / buffer_hours on a task (estimate=duration
// and status go through the core task PATCH). AssigneeID == "" clears it.
func (s *Store) UpdateTaskPlanner(ctx context.Context, taskID string, req *model.UpdateTaskPlannerRequest) (bool, error) {
	set := []string{}
	args := []any{}
	i := 1
	if req.AssigneeID != nil {
		if *req.AssigneeID == "" {
			set = append(set, "assignee_id = NULL")
		} else {
			set = append(set, fmt.Sprintf("assignee_id = $%d", i))
			args = append(args, *req.AssigneeID)
			i++
		}
	}
	if req.BufferHours != nil {
		set = append(set, fmt.Sprintf("buffer_hours = $%d", i))
		args = append(args, *req.BufferHours)
		i++
	}
	if req.PlannerPriority != nil {
		set = append(set, fmt.Sprintf("props = jsonb_set(COALESCE(props, '{}'::jsonb), '{plannerPriority}', to_jsonb($%d::numeric))", i))
		args = append(args, *req.PlannerPriority)
		i++
	}
	if req.Position != nil {
		set = append(set, fmt.Sprintf("position = $%d", i))
		args = append(args, *req.Position)
		i++
	}
	if req.JiraURL != nil {
		if *req.JiraURL == "" {
			set = append(set, "props = COALESCE(props, '{}'::jsonb) - 'jiraUrl'")
		} else {
			set = append(set, fmt.Sprintf("props = jsonb_set(COALESCE(props, '{}'::jsonb), '{jiraUrl}', to_jsonb($%d::text))", i))
			args = append(args, *req.JiraURL)
			i++
		}
	}
	if req.ParentID != nil {
		if *req.ParentID == "" {
			set = append(set, "parent_id = NULL")
		} else {
			if *req.ParentID == taskID {
				return false, ErrReparentCycle
			}
			// Reject if taskID is an ancestor of the new parent (would loop).
			var hit int
			cerr := s.pool.QueryRow(ctx, `
				WITH RECURSIVE anc(id) AS (
					SELECT parent_id FROM tasks WHERE id = $1
					UNION
					SELECT t.parent_id FROM tasks t JOIN anc ON t.id = anc.id
				)
				SELECT 1 FROM anc WHERE id = $2 LIMIT 1
			`, *req.ParentID, taskID).Scan(&hit)
			if cerr == nil {
				return false, ErrReparentCycle
			}
			if cerr != pgx.ErrNoRows {
				return false, cerr
			}
			set = append(set, fmt.Sprintf("parent_id = $%d", i))
			args = append(args, *req.ParentID)
			i++
		}
	}
	if len(set) == 0 {
		return true, nil
	}
	args = append(args, taskID)
	q := "UPDATE tasks SET " + strings.Join(set, ", ") + fmt.Sprintf(" WHERE id = $%d", i)
	tag, err := s.pool.Exec(ctx, q, args...)
	return tag.RowsAffected() > 0, err
}

// ─── Schedule compute + persist ──────────────────────────────────────────────

func dateToMillis(s string) *int64 {
	if s == "" {
		return nil
	}
	t, err := time.Parse("2006-01-02", s)
	if err != nil {
		return nil
	}
	ms := t.UTC().UnixMilli()
	return &ms
}

// ComputeSchedule loads the workspace's planner inputs, runs the engine,
// persists scheduled_start/end onto tasks, and returns enriched rows for the
// schedule view / CSV. CLOSED tasks are excluded (done work doesn't occupy
// future capacity).
func (s *Store) ComputeSchedule(ctx context.Context, userID, startDate string) ([]model.ScheduleRow, error) {
	// 1. Tasks (non-closed).
	type row struct {
		id         string
		parentID   *string
		title      string
		status     string
		assigneeID *string
		duration   *float64
		buffer     *float64
		priority   float64
		position   float64
		dueDate    *int64
		jiraURL    *string
	}
	taskRows, err := s.pool.Query(ctx, `
		SELECT id, parent_id, title, status, assignee_id, duration, buffer_hours,
		       COALESCE((props->>'plannerPriority')::numeric, 0) AS planner_priority,
		       COALESCE(position, created_at) AS position, due_date,
		       props->>'jiraUrl' AS jira_url
		FROM tasks WHERE user_id = $1
		ORDER BY COALESCE(position, created_at)
	`, userID)
	if err != nil {
		return nil, err
	}
	var rows []row
	for taskRows.Next() {
		var r row
		if err := taskRows.Scan(&r.id, &r.parentID, &r.title, &r.status, &r.assigneeID, &r.duration, &r.buffer, &r.priority, &r.position, &r.dueDate, &r.jiraURL); err != nil {
			taskRows.Close()
			return nil, err
		}
		rows = append(rows, r)
	}
	taskRows.Close()
	if err := taskRows.Err(); err != nil {
		return nil, err
	}

	// 2. Dependencies among this user's tasks.
	depRows, err := s.pool.Query(ctx, `
		SELECT td.task_id, td.depends_on_id
		FROM task_dependencies td JOIN tasks t ON t.id = td.task_id
		WHERE t.user_id = $1
	`, userID)
	if err != nil {
		return nil, err
	}
	blockedBy := map[string][]string{}
	for depRows.Next() {
		var tid, did string
		if err := depRows.Scan(&tid, &did); err != nil {
			depRows.Close()
			return nil, err
		}
		blockedBy[tid] = append(blockedBy[tid], did)
	}
	depRows.Close()

	// 3. People.
	persons := map[string]planner.Person{}
	names := map[string]string{}
	pRows, err := s.pool.Query(ctx, `SELECT id, name, hours_per_day FROM people WHERE user_id = $1 AND active = true`, userID)
	if err != nil {
		return nil, err
	}
	for pRows.Next() {
		var id, name string
		var hpd float64
		if err := pRows.Scan(&id, &name, &hpd); err != nil {
			pRows.Close()
			return nil, err
		}
		persons[id] = planner.Person{ID: id, HoursPerDay: hpd}
		names[id] = name
	}
	pRows.Close()

	// 4. Calendar + holidays.
	cal, err := s.GetOrCreateCalendar(ctx, userID)
	if err != nil {
		return nil, err
	}
	holidays := map[string]bool{}
	hols, err := s.ListHolidays(ctx, cal.ID)
	if err != nil {
		return nil, err
	}
	for _, h := range hols {
		holidays[h.Day] = true
	}

	// 5. Time off.
	timeOff := map[string][]planner.TimeOff{}
	toRows, err := s.pool.Query(ctx, `
		SELECT pto.person_id, pto.start_day::text, pto.end_day::text, pto.hours_off
		FROM person_time_off pto JOIN people p ON p.id = pto.person_id
		WHERE p.user_id = $1
	`, userID)
	if err != nil {
		return nil, err
	}
	for toRows.Next() {
		var pid, sd, ed string
		var ho *float64
		if err := toRows.Scan(&pid, &sd, &ed, &ho); err != nil {
			toRows.Close()
			return nil, err
		}
		timeOff[pid] = append(timeOff[pid], planner.TimeOff{Start: sd, End: ed, HoursOff: ho})
	}
	toRows.Close()

	// 6. Build input + run engine.
	in := planner.Input{StartDate: startDate, Persons: persons, TimeOff: timeOff, Calendar: planner.Calendar{WeekendDays: cal.WeekendDays, Holidays: holidays}}
	for _, r := range rows {
		if r.status == "CLOSED" {
			continue // done work doesn't get scheduled or occupy capacity
		}
		t := planner.Task{ID: r.id, EstimateHours: deref(r.duration), BufferHours: deref(r.buffer), BlockedBy: blockedBy[r.id], Priority: r.priority, Position: r.position}
		if r.parentID != nil {
			t.ParentID = *r.parentID
		}
		if r.assigneeID != nil {
			t.AssigneeID = *r.assigneeID
		}
		in.Tasks = append(in.Tasks, t)
	}
	sched, err := planner.Schedule(in)
	if err != nil {
		return nil, err
	}

	// 7. Persist scheduled dates.
	for id, sc := range sched {
		_, err := s.pool.Exec(ctx, `UPDATE tasks SET scheduled_start = $1, scheduled_end = $2 WHERE id = $3`,
			dateToMillis(sc.Start), dateToMillis(sc.End), id)
		if err != nil {
			return nil, err
		}
	}

	// 8. Rolled-up estimate for parents = sum of descendant leaf estimates.
	childIDs := map[string][]string{}
	durByID := map[string]float64{}
	for _, r := range rows {
		if r.parentID != nil {
			childIDs[*r.parentID] = append(childIDs[*r.parentID], r.id)
		}
		durByID[r.id] = deref(r.duration)
	}
	var rolled func(id string) float64
	rolled = func(id string) float64 {
		kids := childIDs[id]
		if len(kids) == 0 {
			return durByID[id]
		}
		var sum float64
		for _, k := range kids {
			sum += rolled(k)
		}
		return sum
	}

	// 9. Enriched rows.
	out := make([]model.ScheduleRow, 0, len(rows))
	for _, r := range rows {
		sc := sched[r.id]
		est := r.duration
		if len(childIDs[r.id]) > 0 {
			s := rolled(r.id)
			est = &s
		}
		row := model.ScheduleRow{
			TaskID: r.id, Title: r.title, ParentID: r.parentID, AssigneeID: r.assigneeID,
			EstimateHours: est, BufferHours: r.buffer, DependencyCount: len(blockedBy[r.id]), Priority: r.priority, Position: r.position, Status: r.status,
			Start: sc.Start, End: sc.End, OnCriticalPath: sc.OnCriticalPath, DueDate: r.dueDate, JiraURL: r.jiraURL,
		}
		if r.assigneeID != nil {
			if n, ok := names[*r.assigneeID]; ok {
				row.AssigneeName = &n
			}
		}
		out = append(out, row)
	}
	sortScheduleRows(out)
	return out, nil
}

func deref(f *float64) float64 {
	if f == nil {
		return 0
	}
	return *f
}

// sortScheduleRows orders by start date (unscheduled last), then assignee name.
func sortScheduleRows(rows []model.ScheduleRow) {
	for i := 1; i < len(rows); i++ {
		for j := i; j > 0 && scheduleLess(rows[j], rows[j-1]); j-- {
			rows[j], rows[j-1] = rows[j-1], rows[j]
		}
	}
}

func scheduleLess(a, b model.ScheduleRow) bool {
	// scheduled before unscheduled
	if (a.Start == "") != (b.Start == "") {
		return a.Start != ""
	}
	if a.Start != b.Start {
		return a.Start < b.Start
	}
	an, bn := "", ""
	if a.AssigneeName != nil {
		an = *a.AssigneeName
	}
	if b.AssigneeName != nil {
		bn = *b.AssigneeName
	}
	return an < bn
}
