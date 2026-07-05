// Package planner is the constraint-based scheduling engine. The core
// Schedule function is pure (no DB, no I/O) so it is fully unit-testable; a
// thin store adapter loads inputs and persists the computed dates separately.
//
// Model (see docs/PLANNER_DESIGN.md):
//   - Manager inputs: estimate hours, assignee, dependencies, parent buffer.
//   - Engine computes scheduled start/end + critical path from those plus a
//     shared calendar (weekends + holidays) and per-person time off.
//   - Placement: a priority-driven, resource-constrained ready-list. Among
//     tasks whose dependencies are resolved, the most important (lowest
//     Priority, then Position) grabs its assignee's next free slot.
//   - Hour-native: each person has a per-day hour budget; independent tasks
//     pack intra-day (two 4h tasks share one 8h day) and spill across days,
//     honouring weekends, holidays, and time off.
//   - Simplifications (documented): dependencies are finish-to-start at *day*
//     granularity (a successor starts the day after its blocker ends, not the
//     same afternoon); critical path is dependency-based, not resource-aware.
package planner

import (
	"errors"
	"fmt"
	"math"
	"time"
)

const dateFmt = "2006-01-02"
const maxScheduleDays = 3650 // ~10y guard against zero-capacity infinite loops

// ─── Inputs (pure, in-memory) ────────────────────────────────────────────────

type Person struct {
	ID          string
	HoursPerDay float64
}

type TimeOff struct {
	Start    string   // YYYY-MM-DD inclusive
	End      string   // YYYY-MM-DD inclusive
	HoursOff *float64 // nil = full day(s) off; else hours removed per day
}

type Calendar struct {
	WeekendDays int             // bitmask Mon=1..Sun=64
	Holidays    map[string]bool // "YYYY-MM-DD" set
}

type Task struct {
	ID            string
	ParentID      string // "" if root
	AssigneeID    string // "" if unassigned
	EstimateHours float64
	BufferHours   float64  // applied on nodes with children
	BlockedBy     []string // task IDs this task depends on
	// Priority drives resource contention: when several ready tasks compete for
	// the same person, the lowest Priority value wins (lower = more important,
	// Jira-style). 0 means "unset" and sorts last. Position (the manual tree
	// order) is the deterministic tie-break.
	Priority float64
	Position float64
}

type Input struct {
	StartDate string // project anchor, YYYY-MM-DD
	Tasks     []Task
	Persons   map[string]Person
	TimeOff   map[string][]TimeOff // personID -> ranges
	Calendar  Calendar
}

// Scheduled is the computed result for one task.
type Scheduled struct {
	Start          string `json:"start"` // YYYY-MM-DD
	End            string `json:"end"`   // YYYY-MM-DD
	OnCriticalPath bool   `json:"onCriticalPath"`
}

// ─── Availability ────────────────────────────────────────────────────────────

func weekdayBit(d time.Time) int {
	// Monday=bit0(1) .. Sunday=bit6(64). time.Weekday: Sun=0..Sat=6.
	return 1 << ((int(d.Weekday()) + 6) % 7)
}

func inRange(day, start, end time.Time) bool {
	return !day.Before(start) && !day.After(end)
}

// availableHours returns how many hours a person can work on a given day.
func (in Input) availableHours(personID string, day time.Time) float64 {
	if in.Calendar.WeekendDays&weekdayBit(day) != 0 {
		return 0
	}
	if in.Calendar.Holidays[day.Format(dateFmt)] {
		return 0
	}
	p, ok := in.Persons[personID]
	if !ok {
		return 0
	}
	base := p.HoursPerDay
	for _, off := range in.TimeOff[personID] {
		s, err1 := time.Parse(dateFmt, off.Start)
		e, err2 := time.Parse(dateFmt, off.End)
		if err1 != nil || err2 != nil || !inRange(day, s, e) {
			continue
		}
		if off.HoursOff == nil {
			return 0
		}
		base -= *off.HoursOff
	}
	if base < 0 {
		return 0
	}
	return base
}

// clock is a person's position on their working timeline: the current day and
// how many hours they've already committed on that day. It lets independent
// tasks pack intra-day (two 4h tasks on one 8h day) instead of each burning a
// whole day.
type clock struct {
	day  time.Time
	used float64
}

// remainingToday returns the person's still-free hours on the clock's day.
func (in Input) remainingToday(personID string, clk clock) float64 {
	return in.availableHours(personID, clk.day) - clk.used
}

// advanceToCapacity moves the clock forward to the next day (from `earliest`
// onward) on which the person has any free hours.
func (in Input) advanceToCapacity(personID string, clk clock, earliest time.Time) (clock, error) {
	if clk.day.Before(earliest) {
		clk = clock{day: earliest}
	}
	for i := 0; in.remainingToday(personID, clk) <= 1e-9; i++ {
		if i > maxScheduleDays {
			return clock{}, fmt.Errorf("no working capacity for person %q", personID)
		}
		clk = clock{day: clk.day.AddDate(0, 0, 1)}
	}
	return clk, nil
}

// place schedules `hours` of effort for `personID`, resuming from the person's
// `clk` but no earlier than `earliest` (a dependency-derived day). It packs
// hour-by-hour across working days and returns the task's start/end dates plus
// the person's advanced clock.
func (in Input) place(personID string, clk clock, earliest time.Time, hours float64) (time.Time, time.Time, clock, error) {
	clk, err := in.advanceToCapacity(personID, clk, earliest)
	if err != nil {
		return time.Time{}, time.Time{}, clock{}, err
	}
	start := clk.day
	if hours <= 1e-9 {
		return start, start, clk, nil // zero-effort milestone: no capacity consumed
	}
	remaining := hours
	end := clk.day
	for i := 0; ; i++ {
		if i > maxScheduleDays {
			return time.Time{}, time.Time{}, clock{}, fmt.Errorf("schedule did not converge for person %q", personID)
		}
		free := in.remainingToday(personID, clk)
		if free > 1e-9 {
			take := math.Min(free, remaining)
			clk.used += take
			remaining -= take
			end = clk.day
			if remaining <= 1e-9 {
				return start, end, clk, nil
			}
		}
		clk = clock{day: clk.day.AddDate(0, 0, 1)}
	}
}

// ─── Schedule ────────────────────────────────────────────────────────────────

// Schedule computes start/end dates + critical-path flags for every task.
func Schedule(in Input) (map[string]Scheduled, error) {
	projectStart, err := time.Parse(dateFmt, in.StartDate)
	if err != nil {
		return nil, fmt.Errorf("invalid startDate: %w", err)
	}

	byID := make(map[string]Task, len(in.Tasks))
	hasChildren := make(map[string]bool)
	for _, t := range in.Tasks {
		byID[t.ID] = t
		if t.ParentID != "" {
			hasChildren[t.ParentID] = true
		}
	}
	isLeaf := func(id string) bool { return !hasChildren[id] }

	// topoSortLeaves is kept purely for cycle detection; the actual placement
	// order is decided by the priority-driven ready-list below.
	if _, err := topoSortLeaves(in.Tasks, isLeaf); err != nil {
		return nil, err
	}

	res := make(map[string]Scheduled, len(in.Tasks))
	endDate := make(map[string]time.Time)
	startDate := make(map[string]time.Time)
	cursor := make(map[string]clock) // assignee -> position on their timeline

	if err := in.scheduleLeaves(byID, isLeaf, projectStart, startDate, endDate, cursor, res); err != nil {
		return nil, err
	}

	// Roll up parents (deepest first) + apply buffers.
	rollUpParents(in.Tasks, byID, hasChildren, startDate, endDate, in)

	// Write rolled-up parent dates into the result — only when the parent
	// actually had scheduled descendants (else leave it unscheduled, not a
	// zero-value 0001-01-01 date).
	for _, t := range in.Tasks {
		if !hasChildren[t.ID] {
			continue
		}
		s, ok := startDate[t.ID]
		if !ok {
			continue
		}
		res[t.ID] = Scheduled{
			Start: s.Format(dateFmt),
			End:   endDate[t.ID].Format(dateFmt),
		}
	}

	markCriticalPath(in.Tasks, byID, hasChildren, startDate, endDate, res)
	return res, nil
}

// scheduleLeaves places every leaf using a priority-driven, resource-constrained
// ready-list: repeatedly, among leaves whose dependencies are all resolved, it
// picks the most important one (lowest Priority, then Position, then input order)
// and gives it its assignee's next free slot. This is what makes higher-priority
// work win contention for a shared person.
func (in Input) scheduleLeaves(
	byID map[string]Task, isLeaf func(string) bool, projectStart time.Time,
	startDate, endDate map[string]time.Time, cursor map[string]clock, res map[string]Scheduled,
) error {
	var leaves []Task
	leafSet := map[string]bool{}
	for _, t := range in.Tasks {
		if isLeaf(t.ID) {
			leaves = append(leaves, t)
			leafSet[t.ID] = true
		}
	}
	idx := map[string]int{}
	for i, t := range leaves {
		idx[t.ID] = i
	}
	resolved := map[string]bool{} // leaf processed (scheduled or skipped)
	ready := func(t Task) bool {
		for _, dep := range t.BlockedBy {
			if leafSet[dep] && !resolved[dep] {
				return false
			}
		}
		return true
	}
	prioKey := func(t Task) float64 {
		if t.Priority == 0 {
			return math.Inf(1) // unset → lowest priority
		}
		return t.Priority
	}
	better := func(a, b Task) bool { // should a be scheduled before b?
		if ka, kb := prioKey(a), prioKey(b); ka != kb {
			return ka < kb
		}
		if a.Position != b.Position {
			return a.Position < b.Position
		}
		return idx[a.ID] < idx[b.ID]
	}

	for range leaves {
		var pick *Task
		for i := range leaves {
			if t := leaves[i]; !resolved[t.ID] && ready(t) && (pick == nil || better(t, *pick)) {
				pick = &leaves[i]
			}
		}
		if pick == nil {
			break // no ready task (cycle already rejected upstream) — stop safely
		}
		t := *pick
		resolved[t.ID] = true
		// Unschedulable leaves (no/unknown assignee) resolve without dates so
		// their successors can still proceed.
		if t.AssigneeID == "" {
			continue
		}
		if _, ok := in.Persons[t.AssigneeID]; !ok {
			continue
		}
		earliest := projectStart
		for _, dep := range t.BlockedBy {
			if de, ok := endDate[dep]; ok {
				if next := de.AddDate(0, 0, 1); next.After(earliest) { // finish-to-start (day granularity)
					earliest = next
				}
			}
		}
		s, e, clk, err := in.place(t.AssigneeID, cursor[t.AssigneeID], earliest, t.EstimateHours)
		if err != nil {
			return err
		}
		startDate[t.ID], endDate[t.ID] = s, e
		cursor[t.AssigneeID] = clk
		res[t.ID] = Scheduled{Start: s.Format(dateFmt), End: e.Format(dateFmt)}
	}
	return nil
}

// topoSortLeaves returns leaf task IDs in dependency order (blockers first).
func topoSortLeaves(tasks []Task, isLeaf func(string) bool) ([]string, error) {
	leaves := map[string]Task{}
	for _, t := range tasks {
		if isLeaf(t.ID) {
			leaves[t.ID] = t
		}
	}
	const (
		white = 0
		gray  = 1
		black = 2
	)
	color := map[string]int{}
	var order []string
	var visit func(id string) error
	visit = func(id string) error {
		switch color[id] {
		case gray:
			return errors.New("dependency cycle detected")
		case black:
			return nil
		}
		color[id] = gray
		for _, dep := range leaves[id].BlockedBy {
			if _, ok := leaves[dep]; ok {
				if err := visit(dep); err != nil {
					return err
				}
			}
		}
		color[id] = black
		order = append(order, id)
		return nil
	}
	// Deterministic: iterate in input order.
	for _, t := range tasks {
		if _, ok := leaves[t.ID]; ok {
			if err := visit(t.ID); err != nil {
				return nil, err
			}
		}
	}
	return order, nil
}

// rollUpParents sets each parent's start = earliest child start, end = latest
// child end, then extends end by the parent's buffer over the team calendar.
func rollUpParents(tasks []Task, byID map[string]Task, hasChildren map[string]bool,
	startDate, endDate map[string]time.Time, in Input) {

	children := map[string][]string{}
	for _, t := range tasks {
		if t.ParentID != "" {
			children[t.ParentID] = append(children[t.ParentID], t.ID)
		}
	}
	// Process by depth descending so nested parents roll up correctly.
	var depth func(id string) int
	depth = func(id string) int {
		t := byID[id]
		if t.ParentID == "" {
			return 0
		}
		return 1 + depth(t.ParentID)
	}
	parents := []string{}
	for id := range children {
		parents = append(parents, id)
	}
	// sort by depth desc (simple insertion; parent counts are small)
	for i := 1; i < len(parents); i++ {
		for j := i; j > 0 && depth(parents[j]) > depth(parents[j-1]); j-- {
			parents[j], parents[j-1] = parents[j-1], parents[j]
		}
	}
	for _, pid := range parents {
		var minS, maxE time.Time
		first := true
		for _, c := range children[pid] {
			cs, okS := startDate[c]
			ce, okE := endDate[c]
			if !okS || !okE {
				continue
			}
			if first {
				minS, maxE, first = cs, ce, false
				continue
			}
			if cs.Before(minS) {
				minS = cs
			}
			if ce.After(maxE) {
				maxE = ce
			}
		}
		if first {
			continue // no scheduled children
		}
		// Apply buffer over the team calendar (weekends/holidays only, 8h/day).
		if buf := byID[pid].BufferHours; buf > 0 {
			maxE = in.advanceTeamHours(maxE, buf)
		}
		startDate[pid], endDate[pid] = minS, maxE
	}
}

// advanceTeamHours extends a date by `hours` of team working time (8h/day,
// skipping weekends and holidays; no person-specific OOO).
func (in Input) advanceTeamHours(from time.Time, hours float64) time.Time {
	const teamHoursPerDay = 8.0
	remaining := hours
	cur := from
	end := from
	for i := 0; remaining > 1e-9 && i < maxScheduleDays; i++ {
		cur = cur.AddDate(0, 0, 1)
		if in.Calendar.WeekendDays&weekdayBit(cur) != 0 || in.Calendar.Holidays[cur.Format(dateFmt)] {
			continue
		}
		remaining -= teamHoursPerDay
		end = cur
	}
	return end
}

// markCriticalPath flags the dependency-based critical path: leaves finishing
// at the makespan, traced back through blockers whose finish bound the
// successor's start. Parents are critical if any descendant leaf is.
func markCriticalPath(tasks []Task, byID map[string]Task, hasChildren map[string]bool,
	startDate, endDate map[string]time.Time, res map[string]Scheduled) {

	var makespan time.Time
	for _, t := range tasks {
		if hasChildren[t.ID] {
			continue
		}
		if e, ok := endDate[t.ID]; ok && e.After(makespan) {
			makespan = e
		}
	}
	critical := map[string]bool{}
	var trace func(id string)
	trace = func(id string) {
		if critical[id] {
			return
		}
		critical[id] = true
		for _, dep := range byID[id].BlockedBy {
			de, ok := endDate[dep]
			if !ok {
				continue
			}
			// blocker is critical if its finish drove this task's start
			if de.AddDate(0, 0, 1).Equal(startDate[id]) {
				trace(dep)
			}
		}
	}
	for _, t := range tasks {
		if hasChildren[t.ID] {
			continue
		}
		if e, ok := endDate[t.ID]; ok && e.Equal(makespan) {
			trace(t.ID)
		}
	}
	// Propagate to ancestors.
	for _, t := range tasks {
		if critical[t.ID] {
			for pid := t.ParentID; pid != ""; pid = byID[pid].ParentID {
				critical[pid] = true
			}
		}
	}
	for id, c := range critical {
		if c {
			s := res[id]
			s.OnCriticalPath = true
			res[id] = s
		}
	}
}
