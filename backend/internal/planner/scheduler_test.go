package planner

import "testing"

// 2026-07-06 is a Monday; 2026-07-10 is a Friday. Weekend bitmask 96 = Sat+Sun.

func p8(id string) Person { return Person{ID: id, HoursPerDay: 8} }

func run(t *testing.T, in Input) map[string]Scheduled {
	t.Helper()
	res, err := Schedule(in)
	if err != nil {
		t.Fatalf("Schedule error: %v", err)
	}
	return res
}

func TestSingleTaskTwoDays(t *testing.T) {
	res := run(t, Input{
		StartDate: "2026-07-06",
		Tasks:     []Task{{ID: "a", AssigneeID: "p", EstimateHours: 16}},
		Persons:   map[string]Person{"p": p8("p")},
		Calendar:  Calendar{WeekendDays: 96},
	})
	if res["a"].Start != "2026-07-06" || res["a"].End != "2026-07-07" {
		t.Errorf("16h @ 8h/day Mon → want Mon..Tue, got %+v", res["a"])
	}
}

func TestDependencySerializationAndParallel(t *testing.T) {
	res := run(t, Input{
		StartDate: "2026-07-06",
		Tasks: []Task{
			{ID: "a", AssigneeID: "p1", EstimateHours: 8},
			{ID: "b", AssigneeID: "p1", EstimateHours: 8, BlockedBy: []string{"a"}},
			{ID: "c", AssigneeID: "p2", EstimateHours: 8},
		},
		Persons:  map[string]Person{"p1": p8("p1"), "p2": p8("p2")},
		Calendar: Calendar{WeekendDays: 96},
	})
	if res["a"].Start != "2026-07-06" || res["a"].End != "2026-07-06" {
		t.Errorf("a want Mon..Mon, got %+v", res["a"])
	}
	if res["b"].Start != "2026-07-07" { // finish-to-start after a
		t.Errorf("b want start Tue (after a), got %+v", res["b"])
	}
	if res["c"].Start != "2026-07-06" { // different person → parallel
		t.Errorf("c want start Mon (parallel), got %+v", res["c"])
	}
	// Critical path: b finishes last; a→b is the critical chain; c is not.
	if !res["b"].OnCriticalPath || !res["a"].OnCriticalPath {
		t.Errorf("a and b should be on critical path: a=%v b=%v", res["a"].OnCriticalPath, res["b"].OnCriticalPath)
	}
	if res["c"].OnCriticalPath {
		t.Errorf("c should not be on critical path")
	}
}

func TestSamePersonSerializes(t *testing.T) {
	res := run(t, Input{
		StartDate: "2026-07-06",
		Tasks: []Task{
			{ID: "a", AssigneeID: "p", EstimateHours: 8},
			{ID: "b", AssigneeID: "p", EstimateHours: 8}, // no dep, same person
		},
		Persons:  map[string]Person{"p": p8("p")},
		Calendar: Calendar{WeekendDays: 96},
	})
	if res["a"].End == res["b"].Start {
		t.Errorf("same person must not overlap; a=%+v b=%+v", res["a"], res["b"])
	}
	if res["b"].Start != "2026-07-07" {
		t.Errorf("b should be pushed to Tue by resource serialization, got %+v", res["b"])
	}
}

func TestWeekendSkip(t *testing.T) {
	res := run(t, Input{
		StartDate: "2026-07-10", // Friday
		Tasks:     []Task{{ID: "a", AssigneeID: "p", EstimateHours: 16}},
		Persons:   map[string]Person{"p": p8("p")},
		Calendar:  Calendar{WeekendDays: 96},
	})
	// Fri 8h, skip Sat/Sun, Mon 8h → end Mon 2026-07-13
	if res["a"].Start != "2026-07-10" || res["a"].End != "2026-07-13" {
		t.Errorf("want Fri..Mon across weekend, got %+v", res["a"])
	}
}

func TestHolidaySkip(t *testing.T) {
	res := run(t, Input{
		StartDate: "2026-07-06",
		Tasks:     []Task{{ID: "a", AssigneeID: "p", EstimateHours: 8}},
		Persons:   map[string]Person{"p": p8("p")},
		Calendar:  Calendar{WeekendDays: 96, Holidays: map[string]bool{"2026-07-06": true}},
	})
	if res["a"].Start != "2026-07-07" { // Monday is a holiday → start Tuesday
		t.Errorf("holiday Mon should push start to Tue, got %+v", res["a"])
	}
}

func TestHalfDayTimeOff(t *testing.T) {
	four := 4.0
	res := run(t, Input{
		StartDate: "2026-07-06",
		Tasks:     []Task{{ID: "a", AssigneeID: "p", EstimateHours: 16}},
		Persons:   map[string]Person{"p": p8("p")},
		TimeOff:   map[string][]TimeOff{"p": {{Start: "2026-07-07", End: "2026-07-07", HoursOff: &four}}},
		Calendar:  Calendar{WeekendDays: 96},
	})
	// Mon 8h, Tue 4h (half off), Wed 4h → end Wed 2026-07-08
	if res["a"].End != "2026-07-08" {
		t.Errorf("half-day OOO should extend to Wed, got %+v", res["a"])
	}
}

func TestParentRollupWithBuffer(t *testing.T) {
	res := run(t, Input{
		StartDate: "2026-07-06",
		Tasks: []Task{
			{ID: "P", EstimateHours: 0, BufferHours: 8}, // parent w/ 1-day buffer
			{ID: "a", ParentID: "P", AssigneeID: "p", EstimateHours: 8},
		},
		Persons:  map[string]Person{"p": p8("p")},
		Calendar: Calendar{WeekendDays: 96},
	})
	// child a: Mon..Mon. Parent start=Mon, end = Mon + 8h buffer = Tue.
	if res["P"].Start != "2026-07-06" || res["P"].End != "2026-07-07" {
		t.Errorf("parent rollup+buffer want Mon..Tue, got %+v", res["P"])
	}
}

func TestCycleRejected(t *testing.T) {
	_, err := Schedule(Input{
		StartDate: "2026-07-06",
		Tasks: []Task{
			{ID: "a", AssigneeID: "p", EstimateHours: 8, BlockedBy: []string{"b"}},
			{ID: "b", AssigneeID: "p", EstimateHours: 8, BlockedBy: []string{"a"}},
		},
		Persons:  map[string]Person{"p": p8("p")},
		Calendar: Calendar{WeekendDays: 96},
	})
	if err == nil {
		t.Errorf("expected cycle error, got nil")
	}
}
