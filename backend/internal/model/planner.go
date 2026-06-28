package model

// Planner domain: people pool, a shared calendar (weekends + company
// holidays), per-person time off, and task dependencies. See
// docs/PLANNER_DESIGN.md (People & calendar model) and PLANNER_IMPLEMENTATION.md.

// Person is a scheduling resource (not a user account). The manager is the
// sole writer.
type Person struct {
	ID          string  `json:"id"`
	UserID      string  `json:"userId"`
	Name        string  `json:"name"`
	Email       *string `json:"email"`
	HoursPerDay float64 `json:"hoursPerDay"`
	Active      bool    `json:"active"`
	CreatedAt   int64   `json:"createdAt"`
	UpdatedAt   int64   `json:"updatedAt"`
}

type CreatePersonRequest struct {
	UserID      string   `json:"userId"`
	Name        string   `json:"name"`
	Email       *string  `json:"email,omitempty"`
	HoursPerDay *float64 `json:"hoursPerDay,omitempty"`
}

type UpdatePersonRequest struct {
	Name        *string  `json:"name,omitempty"`
	Email       *string  `json:"email,omitempty"`
	HoursPerDay *float64 `json:"hoursPerDay,omitempty"`
	Active      *bool    `json:"active,omitempty"`
}

// TimeOff is a person's OOO range. hoursOff NULL = full day(s) off; a value =
// partial/half-day (that many hours removed per day in the range).
type TimeOff struct {
	ID        string   `json:"id"`
	PersonID  string   `json:"personId"`
	StartDay  string   `json:"startDay"` // YYYY-MM-DD
	EndDay    string   `json:"endDay"`   // YYYY-MM-DD, inclusive
	HoursOff  *float64 `json:"hoursOff"`
	Note      *string  `json:"note"`
	CreatedAt int64    `json:"createdAt"`
	UpdatedAt int64    `json:"updatedAt"`
}

type CreateTimeOffRequest struct {
	StartDay string   `json:"startDay"`
	EndDay   string   `json:"endDay"`
	HoursOff *float64 `json:"hoursOff,omitempty"`
	Note     *string  `json:"note,omitempty"`
}

// Calendar is the single shared workspace calendar: a weekend definition plus
// a company-holidays section.
type Calendar struct {
	ID          string `json:"id"`
	UserID      string `json:"userId"`
	WeekendDays int    `json:"weekendDays"` // bitmask Mon=1..Sun=64; Sat+Sun=96
	CreatedAt   int64  `json:"createdAt"`
	UpdatedAt   int64  `json:"updatedAt"`
}

// UpsertCalendarRequest sets the weekend definition for a workspace's calendar
// (created on first write).
type UpsertCalendarRequest struct {
	UserID      string `json:"userId"`
	WeekendDays *int   `json:"weekendDays,omitempty"`
}

type CompanyHoliday struct {
	ID         string  `json:"id"`
	CalendarID string  `json:"calendarId"`
	Day        string  `json:"day"` // YYYY-MM-DD
	Name       *string `json:"name"`
	CreatedAt  int64   `json:"createdAt"`
}

type CreateHolidayRequest struct {
	Day  string  `json:"day"`
	Name *string `json:"name,omitempty"`
}

// TaskDependency: task_id is blocked by depends_on_id.
type TaskDependency struct {
	ID          string `json:"id"`
	TaskID      string `json:"taskId"`
	DependsOnID string `json:"dependsOnId"`
	CreatedAt   int64  `json:"createdAt"`
}

type CreateDependencyRequest struct {
	DependsOnID string `json:"dependsOnId"`
}

// UpdateTaskPlannerRequest sets the planner-specific inputs on a task that the
// core task PATCH doesn't cover. (estimate=duration and status go through the
// existing task PATCH.) An AssigneeID of "" clears the assignee.
type UpdateTaskPlannerRequest struct {
	AssigneeID  *string  `json:"assigneeId,omitempty"`
	BufferHours *float64 `json:"bufferHours,omitempty"`
}

// ScheduleRow is one row of the generated execution schedule, enriched for the
// CLI/web schedule view + CSV export.
type ScheduleRow struct {
	TaskID         string   `json:"taskId"`
	Title          string   `json:"title"`
	ParentID       *string  `json:"parentId"`
	AssigneeID     *string  `json:"assigneeId"`
	AssigneeName   *string  `json:"assigneeName"`
	EstimateHours  *float64 `json:"estimateHours"`
	Status         string   `json:"status"`
	Start          string   `json:"start"` // YYYY-MM-DD, empty if unscheduled
	End            string   `json:"end"`
	OnCriticalPath bool     `json:"onCriticalPath"`
}
