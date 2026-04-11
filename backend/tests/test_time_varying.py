"""
Comprehensive unit tests for time_varying.py
==============================================

Tests cover:
- TimeVarying class with bisect-based binary search for O(log n) lookups
- changes_on() method with mutation resistance for 'in'/'not in' operators
- changes_on() with dates before, between, and after change dates
- Edge cases: single step, multiple steps, boundary dates
- Mutation testing targets:
  - Catching 'in' → 'not in' mutations
  - Catching missing _dates initialization
  - Catching dates list consistency

Run with::

    pytest backend/tests/test_time_varying.py -v
    pytest backend/tests/test_time_varying.py -v --cov=time_varying --cov-report=term-missing
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from datetime import date, timedelta
from decimal import Decimal

from time_varying import TimeVarying, TimeStep


# ---------------------------------------------------------------------------
# Helpers / constants used across tests
# ---------------------------------------------------------------------------

# Test dates
DATE_2024_01_01 = date(2024, 1, 1)
DATE_2024_01_02 = date(2024, 1, 2)
DATE_2024_01_15 = date(2024, 1, 15)
DATE_2024_02_01 = date(2024, 2, 1)
DATE_2024_03_01 = date(2024, 3, 1)
DATE_2024_01_03 = date(2024, 1, 3)
DATE_2024_04_01 = date(2024, 4, 1)
DATE_2024_05_01 = date(2024, 5, 1)
DATE_2024_02_20 = date(2024, 2, 20)
DATE_2024_03_15 = date(2024, 3, 15)

# Dates before, between, and after change dates for testing
DATE_2023_12_31 = date(2023, 12, 31)  # Before all change dates
DATE_2024_01_08 = date(2024, 1, 8)    # Between first and second change
DATE_2024_02_15 = date(2024, 2, 15)   # Between second and third change
DATE_2024_06_01 = date(2024, 6, 1)    # After all change dates
VERY_OLD_DATE = date(1900, 1, 1)
VERY_FUTURE_DATE = date(9999, 12, 31)
DATE_2026_03_31 = date(2026, 3, 31)
DATE_2026_04_01 = date(2026, 4, 1)
DATE_2027_07_01 = date(2027, 7, 1)
DATE_2028_10_01 = date(2028, 10, 1)
DATE_2028_11_01 = date(2028, 11, 1)


DEFAULT_STEPS = [
    TimeStep(DATE_2024_01_01, 100),
    TimeStep(DATE_2024_02_01, 200),
    TimeStep(DATE_2024_03_01, 300),
]


# ===========================================================================
# 1. TimeStep Tests
# ===========================================================================

class TestTimeStep:
    """Tests for TimeStep class."""

    def test_create_timestep_with_int(self):
        """TimeStep can be created with integer value."""
        ts = TimeStep(DATE_2024_01_01, 100)
        assert ts.from_date == DATE_2024_01_01
        assert ts.value == 100

    def test_create_timestep_with_decimal(self):
        """TimeStep can be created with Decimal value."""
        ts = TimeStep(DATE_2024_01_01, Decimal("100.50"))
        assert ts.from_date == DATE_2024_01_01
        assert ts.value == Decimal("100.50")

    def test_timestep_equality(self):
        """Two TimeSteps with same date and value are equal."""
        ts1 = TimeStep(DATE_2024_01_01, 100)
        ts2 = TimeStep(DATE_2024_01_01, 100)
        assert ts1 == ts2

    def test_timestep_inequality_different_value(self):
        """TimeSteps with different values are not equal."""
        ts1 = TimeStep(DATE_2024_01_01, 100)
        ts2 = TimeStep(DATE_2024_01_01, 200)
        assert ts1 != ts2


# ===========================================================================
# 2. TimeVarying Initialization and Basic Tests
# ===========================================================================

class TestTimeVaryingInitialization:
    """Tests for TimeVarying initialization."""

    def test_create_with_single_step(self):
        """TimeVarying can be created with a single step."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        assert len(tv.steps) == 1
        assert tv.steps[0].value == 100

    def test_create_with_multiple_steps(self):
        """TimeVarying can be created with multiple steps."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)
        assert len(tv.steps) == 3

    def test_steps_are_sorted_by_date(self):
        """TimeVarying automatically sorts steps by from_date."""
        steps = [
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)
        assert tv.steps[0].from_date == DATE_2024_01_01
        assert tv.steps[1].from_date == DATE_2024_02_01
        assert tv.steps[2].from_date == DATE_2024_03_01

    def test_dates_list_initialized(self):
        """_dates list is properly initialized from steps."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)
        assert hasattr(tv, '_dates')
        assert tv._dates == [DATE_2024_01_01, DATE_2024_02_01]

    def test_dates_list_is_separate_from_steps(self):
        """_dates list is a new list, not a reference to steps."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        # Verify it's a list of dates
        assert isinstance(tv._dates, list)
        assert len(tv._dates) == len(tv.steps)


# ===========================================================================
# 3. changes_on() Method - MUTATION TESTING FOCUS
# ===========================================================================

class TestChangesOnWithChangeDate:
    """
    Tests for changes_on() method with dates that ARE change dates.
    MUTATION TARGET: Catches 'in' → 'not in' mutations
    """

    def test_changes_on_single_change_date(self):
        """changes_on() returns True for the single change date."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_01_01) is True

    def test_changes_on_first_of_multiple_dates(self):
        """changes_on() returns True for the first change date."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_01_01) is True

    def test_changes_on_second_of_multiple_dates(self):
        """changes_on() returns True for the second change date."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_02_01) is True

    def test_changes_on_third_of_multiple_dates(self):
        """changes_on() returns True for the third change date."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_03_01) is True

    def test_changes_on_all_dates_in_five_step_sequence(self):
        """changes_on() returns True for ALL dates in a 5-step sequence."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_04_01, 400),
            TimeStep(DATE_2024_05_01, 500),
        ]
        tv = TimeVarying(steps)

        # Verify EVERY change date returns True
        assert tv.changes_on(DATE_2024_01_01) is True
        assert tv.changes_on(DATE_2024_02_01) is True
        assert tv.changes_on(DATE_2024_03_01) is True
        assert tv.changes_on(DATE_2024_04_01) is True
        assert tv.changes_on(DATE_2024_05_01) is True

        # This test ensures the 'in' operator works, mutation 'in' → 'not in' would fail


# ===========================================================================
# 4. changes_on() Method - NON-CHANGE DATES (Before, Between, After)
# ===========================================================================

class TestChangesOnWithNonChangeDate:
    """
    Tests for changes_on() method with dates that are NOT change dates.
    MUTATION TARGET: Catches 'in' → 'not in' mutations
    MUTATION TARGET: Catches if _dates initialization is missing
    """

    def test_changes_on_date_before_all_changes(self):
        """changes_on() returns False for dates before the first change."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2023_12_31) is False

    def test_changes_on_date_between_changes(self):
        """changes_on() returns False for dates between change dates."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)

        # Test date between first and second change
        assert tv.changes_on(DATE_2024_01_08) is False

        # Test date between second and third change
        assert tv.changes_on(DATE_2024_02_15) is False

    def test_changes_on_date_after_all_changes(self):
        """changes_on() returns False for dates after the last change."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_06_01) is False

    def test_changes_on_multiple_non_changes_with_five_steps(self):
        """changes_on() returns False for multiple non-change dates in a 5-step sequence."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_04_01, 400),
            TimeStep(DATE_2024_05_01, 500),
        ]
        tv = TimeVarying(steps)

        # Verify several non-change dates all return False
        assert tv.changes_on(DATE_2023_12_31) is False  # Before all
        assert tv.changes_on(DATE_2024_01_08) is False  # Between 1st and 2nd
        assert tv.changes_on(DATE_2024_02_15) is False  # Between 2nd and 3rd
        assert tv.changes_on(DATE_2024_06_01) is False  # After all


# ===========================================================================
# 5. changes_on() - Dates Very Close to Change Dates
# ===========================================================================

class TestChangesOnWithAdjacentDates:
    """
    Tests for changes_on() with dates adjacent to change dates.
    Ensures the method is precise and catches off-by-one errors.
    """

    def test_changes_on_day_before_change(self):
        """changes_on() returns False for the day before a change."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        day_before = DATE_2024_01_01 - timedelta(days=1)
        assert tv.changes_on(day_before) is False

    def test_changes_on_day_after_change(self):
        """changes_on() returns False for the day after a change."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        day_after = DATE_2024_01_01 + timedelta(days=1)
        assert tv.changes_on(day_after) is False

    def test_changes_on_exact_change_date(self):
        """changes_on() returns True for the exact change date."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_01_01) is True

    def test_changes_on_adjacent_dates_around_multiple_changes(self):
        """changes_on() correctly distinguishes exact dates from adjacent dates."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)

        # Around first change date
        assert tv.changes_on(DATE_2024_01_01 - timedelta(days=1)) is False
        assert tv.changes_on(DATE_2024_01_01) is True
        assert tv.changes_on(DATE_2024_01_01 + timedelta(days=1)) is False

        # Around second change date
        assert tv.changes_on(DATE_2024_02_01 - timedelta(days=1)) is False
        assert tv.changes_on(DATE_2024_02_01) is True
        assert tv.changes_on(DATE_2024_02_01 + timedelta(days=1)) is False

        # Around third change date
        assert tv.changes_on(DATE_2024_03_01 - timedelta(days=1)) is False
        assert tv.changes_on(DATE_2024_03_01) is True
        assert tv.changes_on(DATE_2024_03_01 + timedelta(days=1)) is False


class TestChangesOnComprehensiveCoverage:
    """Additional mutation-focused coverage for every step date and its neighbors."""

    def test_changes_on_all_step_dates_true(self):
        """Every cached change date returns True for changes_on()."""
        tv = TimeVarying(DEFAULT_STEPS)

        for change_date in tv.all_change_dates():
            assert tv.changes_on(change_date) is True

    def test_changes_on_non_step_dates_false(self):
        """Dates before, between (when gaps exist), and after the cached change dates return False."""
        tv = TimeVarying(DEFAULT_STEPS)
        change_dates = tv.all_change_dates()

        non_change_dates = [change_dates[0] - timedelta(days=1)]
        for prev_date, next_date in zip(change_dates, change_dates[1:]):
            if (next_date - prev_date).days > 1:
                non_change_dates.append(prev_date + timedelta(days=1))
        non_change_dates.append(change_dates[-1] + timedelta(days=1))

        for non_change_date in non_change_dates:
            assert tv.changes_on(non_change_date) is False

    def test_changes_on_nearby_dates_are_precise(self):
        """The days directly adjacent to each change date reject changes_on(), while the exact date is accepted."""
        tv = TimeVarying(DEFAULT_STEPS)

        for change_date in tv.all_change_dates():
            assert tv.changes_on(change_date - timedelta(days=1)) is False
            assert tv.changes_on(change_date) is True
            assert tv.changes_on(change_date + timedelta(days=1)) is False


# ===========================================================================
# 6. changes_on() - Return Type Tests
# ===========================================================================

class TestChangesOnReturnType:
    """Tests for changes_on() return type."""

    def test_changes_on_returns_bool_for_true(self):
        """changes_on() returns a boolean True, not a truthy value."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        result = tv.changes_on(DATE_2024_01_01)
        assert result is True
        assert isinstance(result, bool)

    def test_changes_on_returns_bool_for_false(self):
        """changes_on() returns a boolean False, not a falsy value."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        result = tv.changes_on(DATE_2024_01_08)
        assert result is False
        assert isinstance(result, bool)


# ===========================================================================
# 6. Comprehensive changes_on() Mutation Testing - TestChangesOnMethod
# ===========================================================================

class TestChangesOnMethod:
    """Comprehensive mutation-focused coverage for changes_on()."""

    @staticmethod
    def _build_tv_from_dates(change_dates):
        raw_schedule = [
            {"from": change_date.isoformat(), "value": idx + 1}
            for idx, change_date in enumerate(change_dates)
        ]
        return TimeVarying.from_raw(raw_schedule)

    def test_all_change_dates_return_true(self):
        """Every declared change date reports True for changes_on()."""
        change_dates = [
            DATE_2024_01_01,
            DATE_2024_02_01,
            DATE_2024_03_01,
            DATE_2024_04_01,
            DATE_2024_05_01,
        ]
        tv = self._build_tv_from_dates(change_dates)

        assert len(tv.all_change_dates()) >= 4, "Expected 4+ change dates"
        for change_date in tv.all_change_dates():
            assert tv.changes_on(change_date) is True, (
                f"changes_on({change_date}) should be True for a change date, "
                f"but got {tv.changes_on(change_date)}"
            )

    def test_non_change_dates_return_false(self):
        """Dates before, between, and after the declared changes all return False."""
        change_dates = [
            DATE_2024_01_01,
            DATE_2024_02_01,
            DATE_2024_03_01,
            DATE_2024_04_01,
            DATE_2024_05_01,
        ]
        tv = self._build_tv_from_dates(change_dates)
        all_dates = tv.all_change_dates()

        non_change_dates = [
            all_dates[0] - timedelta(days=5),
            all_dates[0] + timedelta(days=1),
        ]
        for prev_date, next_date in zip(all_dates, all_dates[1:]):
            if (next_date - prev_date).days > 1:
                non_change_dates.append(prev_date + timedelta(days=1))
        non_change_dates.append(all_dates[-1] + timedelta(days=2))

        for non_change_date in non_change_dates:
            assert tv.changes_on(non_change_date) is False, (
                f"changes_on({non_change_date}) should be False (non change date), "
                f"but got {tv.changes_on(non_change_date)}"
            )

    def test_boundary_conditions_day_before_after(self):
        """Day before and after each change date stay False while the change date stays True."""
        change_dates = [
            DATE_2024_01_01,
            DATE_2024_02_01,
            DATE_2024_03_01,
            DATE_2024_04_01,
        ]
        tv = self._build_tv_from_dates(change_dates)

        for change_date in tv.all_change_dates():
            before = change_date - timedelta(days=1)
            after = change_date + timedelta(days=1)

            assert tv.changes_on(before) is False, (
                f"changes_on({before}) should be False (day before {change_date}), "
                f"but got {tv.changes_on(before)}"
            )
            assert tv.changes_on(change_date) is True, (
                f"changes_on({change_date}) should be True, but got {tv.changes_on(change_date)}"
            )
            assert tv.changes_on(after) is False, (
                f"changes_on({after}) should be False (day after {change_date}), "
                f"but got {tv.changes_on(after)}"
            )

    def test_edge_cases_single_change(self):
        """Single-change, date.min, and rapid consecutive changes stay mutation-safe."""
        single_change = DATE_2024_03_15
        tv_single = self._build_tv_from_dates([single_change])

        before_single = single_change - timedelta(days=1)
        after_single = single_change + timedelta(days=1)
        assert tv_single.changes_on(before_single) is False
        assert tv_single.changes_on(single_change) is True
        assert tv_single.changes_on(after_single) is False

        steps_near_min = [
            TimeStep(date.min, "baseline"),
            TimeStep(DATE_2024_01_01, "later"),
        ]
        tv_min = TimeVarying(steps_near_min)
        assert tv_min.changes_on(date.min) is True
        assert tv_min.changes_on(date.min + timedelta(days=1)) is False
        assert tv_min.changes_on(DATE_2024_01_01) is True

        rapid_dates = [
            DATE_2024_01_01,
            DATE_2024_01_02,
            DATE_2024_01_03,
        ]
        tv_rapid = self._build_tv_from_dates(rapid_dates)
        for rapid_date in rapid_dates:
            assert tv_rapid.changes_on(rapid_date) is True
        assert tv_rapid.changes_on(rapid_dates[0] - timedelta(days=1)) is False
        assert tv_rapid.changes_on(rapid_dates[-1] + timedelta(days=1)) is False

# ===========================================================================
# 7. all_change_dates() Method Tests
# ===========================================================================

class TestAllChangeDates:
    """Tests for all_change_dates() method."""

    def test_all_change_dates_returns_list(self):
        """all_change_dates() returns a list."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        result = tv.all_change_dates()
        assert isinstance(result, list)

    def test_all_change_dates_single_date(self):
        """all_change_dates() returns correct single date."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        result = tv.all_change_dates()
        assert result == [DATE_2024_01_01]

    def test_all_change_dates_multiple_dates(self):
        """all_change_dates() returns all dates in correct order."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)
        result = tv.all_change_dates()
        assert result == [DATE_2024_01_01, DATE_2024_02_01, DATE_2024_03_01]

    def test_all_change_dates_returns_new_list(self):
        """all_change_dates() returns a new list, not internal reference."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        result1 = tv.all_change_dates()
        result2 = tv.all_change_dates()
        assert result1 == result2
        assert result1 is not result2  # Different list objects

    def test_all_change_dates_mutation_does_not_affect_internal_state(self):
        """Mutating the returned list does not change TimeVarying internal dates."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)

        dates = tv.all_change_dates()
        dates.pop()  # mutate the returned list

        assert tv.all_change_dates() == [
            DATE_2024_01_01,
            DATE_2024_02_01,
            DATE_2024_03_01,
        ]

    def test_all_change_dates_returns_independent_lists_each_call(self):
        """Each call returns a distinct list that is unaffected by prior mutations."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)

        first = tv.all_change_dates()
        second = tv.all_change_dates()
        first.clear()

        assert second == [DATE_2024_01_01, DATE_2024_02_01]
        assert tv.all_change_dates() == [DATE_2024_01_01, DATE_2024_02_01]

    def test_all_change_dates_sorted(self):
        """Return order aligns with the internally sorted steps."""
        steps = [
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)

        assert tv.all_change_dates() == [
            DATE_2024_01_01,
            DATE_2024_02_01,
            DATE_2024_03_01,
        ]


# ===========================================================================
# 8. resolve() Method Tests (Supporting changes_on tests)
# ===========================================================================

class TestResolve:
    """Tests for resolve() method to ensure consistency with changes_on()."""

    def test_resolve_at_change_date(self):
        """resolve() returns correct value at a change date."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)
        assert tv.resolve(DATE_2024_01_01) == 100
        assert tv.resolve(DATE_2024_02_01) == 200

    def test_resolve_between_change_dates(self):
        """resolve() returns value from previous change date."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        tv = TimeVarying(steps)
        # Between Jan and Feb should return Jan's value
        assert tv.resolve(DATE_2024_01_15) == 100
        # Between Feb and Mar should return Feb's value
        assert tv.resolve(DATE_2024_02_15) == 200

    def test_resolve_raises_for_before_first_date(self):
        """resolve() raises error for dates before the first change."""
        steps = [TimeStep(DATE_2024_01_01, 100)]
        tv = TimeVarying(steps)
        with pytest.raises(ValueError, match="No value defined"):
            tv.resolve(DATE_2023_12_31)

    def test_resolve_boundary_transitions_cover_all_change_points(self):
        """Boundary dates around each change stay tied to the correct step."""
        steps = [
            TimeStep(date.min, "baseline"),
            TimeStep(DATE_2026_04_01, "first change"),
            TimeStep(DATE_2028_10_01, "second change"),
        ]
        tv = TimeVarying(steps)

        # Day before the first change should still return the baseline value.
        assert tv.resolve(DATE_2026_03_31) == "baseline"
        # On the first change date and between the two changes we should get the first change value.
        assert tv.resolve(DATE_2026_04_01) == "first change"
        assert tv.resolve(DATE_2027_07_01) == "first change"
        # On and after the second change date we should resolve to the second change value.
        assert tv.resolve(DATE_2028_10_01) == "second change"
        assert tv.resolve(DATE_2028_11_01) == "second change"


# ===========================================================================
# 9. TimeVarying with Different Value Types
# ===========================================================================

class TestTimeVaryingWithDifferentValueTypes:
    """Tests for TimeVarying with different value types."""

    def test_with_integer_values(self):
        """TimeVarying works with integer values."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_01_01) is True
        assert tv.changes_on(DATE_2024_01_15) is False

    def test_with_float_values(self):
        """TimeVarying works with float values."""
        steps = [
            TimeStep(DATE_2024_01_01, 100.5),
            TimeStep(DATE_2024_02_01, 200.75),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_01_01) is True
        assert tv.changes_on(DATE_2024_01_15) is False

    def test_with_decimal_values(self):
        """TimeVarying works with Decimal values."""
        steps = [
            TimeStep(DATE_2024_01_01, Decimal("100.50")),
            TimeStep(DATE_2024_02_01, Decimal("200.75")),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_01_01) is True
        assert tv.changes_on(DATE_2024_01_15) is False

    def test_with_string_values(self):
        """TimeVarying works with string values."""
        steps = [
            TimeStep(DATE_2024_01_01, "active"),
            TimeStep(DATE_2024_02_01, "inactive"),
        ]
        tv = TimeVarying(steps)
        assert tv.changes_on(DATE_2024_01_01) is True
        assert tv.changes_on(DATE_2024_01_15) is False


# ===========================================================================
# 10. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge case tests for TimeVarying."""

    def test_constant_value_single_step(self):
        """A constant TimeVarying (single step) works correctly."""
        tv = TimeVarying.constant(value=100)

        # Constant value should only change on date.min
        assert tv.changes_on(date.min) is True
        # Any other date should return False
        assert tv.changes_on(DATE_2024_01_01) is False

    def test_unsorted_input_becomes_sorted(self):
        """Unsorted input steps are automatically sorted."""
        steps = [
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(steps)

        # Verify changes_on works correctly with automatically sorted steps
        assert tv.changes_on(DATE_2024_01_01) is True
        assert tv.changes_on(DATE_2024_02_01) is True
        assert tv.changes_on(DATE_2024_03_01) is True

    def test_duplicate_dates_last_value_wins(self):
        """When duplicate dates exist, the last value in input order wins."""
        steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_01_01, 200),  # Duplicate date
        ]
        tv = TimeVarying(steps)

        # Both should still return True for changes_on
        assert tv.changes_on(DATE_2024_01_01) is True
        # The resolve should return the last value at that date
        assert tv.resolve(DATE_2024_01_01) == 200


class TestConstantTimeVarying:
    """Tests focused exclusively on TimeVarying.constant behavior."""

    def test_constant_resolves_on_date_min_and_extremes(self):
        """The constant value should be resolvable for any date."""
        value = Decimal("42.00")
        tv = TimeVarying.constant(value=value)

        assert tv.resolve(date.min) == value
        assert tv.resolve(VERY_OLD_DATE) == value
        assert tv.resolve(VERY_FUTURE_DATE) == value

    def test_constant_changes_on_always_false_for_actual_dates(self):
        """constants effectively have no change dates beyond their sentinel."""
        tv = TimeVarying.constant(value="constant")
        assert tv.changes_on(DATE_2024_01_01) is False
        assert tv.changes_on(DATE_2024_04_01) is False

    def test_constant_all_change_dates_returns_only_date_min(self):
        """all_change_dates() exposes only the original date.min sentinel."""
        tv = TimeVarying.constant(value="constant")
        assert tv.all_change_dates() == [date.min]


class TestTimeVaryingSorting:
    """Ensures initialization always sorts steps and caches dates consistently."""

    def test_unsorted_input_resolves_dates_in_expected_order(self):
        """Unsorted steps still resolve correctly and expose sorted change dates."""
        unsorted_steps = [
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv = TimeVarying(unsorted_steps)

        # resolve should return the values that correspond to sorted dates
        assert tv.resolve(DATE_2024_01_01) == 100
        assert tv.resolve(DATE_2024_02_01) == 200
        assert tv.resolve(DATE_2024_03_01) == 300

        # internal steps list should be sorted by from_date
        expected_order = sorted(unsorted_steps, key=lambda step: step.from_date)
        assert tv.steps == expected_order

        # _dates cache should reflect the sorted order as well
        assert tv.all_change_dates() == [DATE_2024_01_01, DATE_2024_02_01, DATE_2024_03_01]

    def test_last_step_first_input_still_sorts_before_use(self):
        """When the last change is provided first, __init__ still sorts everything."""
        reversed_steps = [
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_01_01, 100),
        ]
        tv = TimeVarying(reversed_steps)

        # resolve should honor the chronological order even if input was reversed
        assert tv.resolve(DATE_2024_01_01) == 100
        assert tv.resolve(DATE_2024_02_01) == 200
        assert tv.resolve(DATE_2024_03_01) == 300

        # verify internal representation is sorted and matches change dates
        expected_sorted_steps = sorted(reversed_steps, key=lambda step: step.from_date)
        assert tv.steps == expected_sorted_steps
        assert tv.all_change_dates() == [DATE_2024_01_01, DATE_2024_02_01, DATE_2024_03_01]

    def test_sorted_and_reverse_inputs_match_results(self):
        """Sorted input and a reversed initializer behave identically."""
        sorted_steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        reversed_steps = [
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_01_01, 100),
        ]

        tv_sorted = TimeVarying(sorted_steps)
        tv_reversed = TimeVarying(reversed_steps)

        check_dates = [
            DATE_2024_01_01,
            DATE_2024_01_15,
            DATE_2024_02_01,
            DATE_2024_02_20,
            DATE_2024_03_01,
        ]
        for check_date in check_dates:
            assert tv_sorted.resolve(check_date) == tv_reversed.resolve(check_date)

        assert tv_sorted.all_change_dates() == tv_reversed.all_change_dates()
        assert tv_sorted.steps == tv_reversed.steps

    def test_sorted_and_unsorted_inputs_produce_same_results(self):
        """Sorted and unsorted constructors yield identical behavior."""
        sorted_steps = [
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
            TimeStep(DATE_2024_03_01, 300),
        ]
        unsorted_steps = [
            TimeStep(DATE_2024_03_01, 300),
            TimeStep(DATE_2024_01_01, 100),
            TimeStep(DATE_2024_02_01, 200),
        ]
        tv_sorted = TimeVarying(sorted_steps)
        tv_unsorted = TimeVarying(unsorted_steps)

        check_dates = [
            DATE_2024_01_01,
            DATE_2024_01_15,
            DATE_2024_02_01,
            DATE_2024_02_20,
            DATE_2024_03_01,
        ]
        for check_date in check_dates:
            assert tv_sorted.resolve(check_date) == tv_unsorted.resolve(check_date)

        assert tv_sorted.all_change_dates() == tv_unsorted.all_change_dates()
        assert tv_sorted.steps == tv_unsorted.steps

# ===========================================================================
# 11. from_raw() Date Parsing Mutation Tests
# ===========================================================================

class TestFromRaw:
    """Mutation-focused tests for TimeVarying.from_raw() date parsing."""

    @pytest.mark.parametrize(
        "invalid_from",
        [
            "2026/04/01",  # wrong separator
            "04-01-2026",  # wrong order (MM-DD-YYYY instead of YYYY-MM-DD)
            "invalid",  # non-date string
            "2026-13-01",  # invalid month
            "2026-02-30",  # invalid day for February
            "2023-02-29",  # non-leap year Feb 29
        ],
        ids=lambda value: f"invalid-{value}",
    )
    def test_invalid_date_formats_raise_value_error(self, invalid_from):
        """from_raw should surface ValueError when the isoformat string is malformed."""
        raw_schedule = [{"from": invalid_from, "value": 1}]

        with pytest.raises(ValueError):
            TimeVarying.from_raw(raw_schedule)

    def test_edge_case_dates_parse_min_max_and_leap_year(self):
        """Min/max dates and a leap-year date should parse successfully."""
        raw_schedule = [
            {"from": date.min.isoformat(), "value": "baseline"},
            {"from": "2024-02-29", "value": "leap"},
            {"from": date.max.isoformat(), "value": "ceiling"},
        ]

        tv = TimeVarying.from_raw(raw_schedule)

        assert tv.changes_on(date.min) is True
        assert tv.resolve(date.min) == "baseline"

        leap_date = date(2024, 2, 29)
        assert tv.changes_on(leap_date) is True
        assert tv.resolve(leap_date) == "leap"
        assert tv.resolve(leap_date + timedelta(days=1)) == "leap"

        assert tv.changes_on(date.max) is True
        assert tv.resolve(date.max) == "ceiling"

    def test_string_dates_match_direct_date_steps(self):
        """ISO strings yield the same behavior as constructing with date objects."""
        raw_schedule = [
            {"from": "2026-04-01", "value": "start"},
            {"from": "2026-04-15", "value": "mid"},
            {"from": "2026-05-01", "value": "end"},
        ]
        tv_from_raw = TimeVarying.from_raw(raw_schedule)

        direct_steps = [
            TimeStep(date(2026, 4, 1), "start"),
            TimeStep(date(2026, 4, 15), "mid"),
            TimeStep(date(2026, 5, 1), "end"),
        ]
        tv_direct = TimeVarying(direct_steps)

        assert tv_from_raw == tv_direct

        check_dates = [
            date(2026, 4, 1),
            date(2026, 4, 14),
            date(2026, 4, 15),
            date(2026, 5, 1),
            date(2026, 5, 2),
        ]
        for check_date in check_dates:
            assert tv_from_raw.resolve(check_date) == tv_direct.resolve(check_date)

    def test_boundary_dates_from_raw_are_exact(self):
        """Day-before/day-after should not be mistaken for the change date itself."""
        raw_schedule = [
            {"from": date.min.isoformat(), "value": "baseline"},
            {"from": "2026-04-01", "value": "first"},
            {"from": "2026-05-01", "value": "second"},
        ]
        tv = TimeVarying.from_raw(raw_schedule)

        for change_date, expected_value in [
            (date(2026, 4, 1), "first"),
            (date(2026, 5, 1), "second"),
        ]:
            before = change_date - timedelta(days=1)
            after = change_date + timedelta(days=1)

            assert tv.changes_on(before) is False
            assert tv.changes_on(change_date) is True
            assert tv.changes_on(after) is False

            assert tv.resolve(change_date) == expected_value
            assert tv.resolve(after) == expected_value


class TestCoerceValueBehavior:
    """Exercise _coerce_value() branches that support mutation testing."""

    class _DecimalStrOnly:
        """Values that only support str() when converted to Decimal."""

        def __str__(self):
            return "3.5"

        def __repr__(self):
            raise AssertionError("repr() must not be used for Decimal conversion")

        def __int__(self):
            raise AssertionError("int() must not be used for Decimal conversion")

        def __float__(self):
            raise AssertionError("float() must not be used for Decimal conversion")

    def test_decimal_coercion_uses_str_for_precision(self):
        """Ensure Decimal conversion preserves precision via str()."""
        result = TimeVarying._coerce_value(3.5, Decimal)
        assert isinstance(result, Decimal)
        assert result == Decimal("3.5")

    def test_decimal_conversion_does_not_call_repr(self):
        """Decimal conversion should rely on str() even when repr() is broken."""
        result = TimeVarying._coerce_value(self._DecimalStrOnly(), Decimal)
        assert result == Decimal("3.5")

    def test_decimal_coercion_avoids_direct_decimal(self):
        """Ensure Decimal coercion still works when Decimal(value) would fail."""
        sentinel = self._DecimalStrOnly()
        with pytest.raises(TypeError):
            Decimal(sentinel)
        result = TimeVarying._coerce_value(sentinel, Decimal)
        assert isinstance(result, Decimal)
        assert result == Decimal("3.5")

    def test_bool_coercion_handles_int_and_str(self):
        """bool() branch should work consistently for ints and strings."""
        assert TimeVarying._coerce_value(1, bool) is True
        assert TimeVarying._coerce_value(0, bool) is False
        assert TimeVarying._coerce_value("true", bool) is True

    def test_generic_types_pass_through(self):
        """Values with generic typing metadata should be returned unchanged."""
        list_ints = [1, 2]
        list_strs = ["x", "y"]
        sample_dict = {"k": 1}

        assert TimeVarying._coerce_value(list_ints, list[int]) is list_ints
        assert TimeVarying._coerce_value(list_strs, list[str]) is list_strs
        assert TimeVarying._coerce_value(sample_dict, dict[str, int]) is sample_dict

    def test_none_type_parameter_passes_through(self):
        """Explicit None type parameter must return the raw value."""
        sentinel = "unchanged"
        assert TimeVarying._coerce_value(sentinel, None) == sentinel
