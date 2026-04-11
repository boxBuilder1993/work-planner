"""
Comprehensive unit tests for employer module.

Tests cover:
- PF calculation with boundary conditions
- TDS calculation with FY boundaries
- Transaction recording with category validation
- State management and updates
- Mutation resistance for:
  - min/max confusion
  - Comparison operators (<, <=, ==, >=, >)
  - Arithmetic operators (+, -, *, /, //, %)
  - Logical operators (and, or)
  - Constants and date offsets
"""

import sys
from pathlib import Path
from datetime import date
from decimal import Decimal

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from backend.finance.institutions.employer import (
    Employer,
    SalaryState,
    Transaction,
    EPFContribution,
    _compute_pf,
    _compute_monthly_tds_with_bonus,
)


# ============================================================================
# PF Calculation Tests
# ============================================================================

class TestComputePFBasic:
    """Tests for basic PF calculation."""

    def test_pf_below_cap(self):
        """Test PF calculation when basic is below cap."""
        # Basic annual = 150000, monthly = 12500, cap = 15000
        # 12500 < 15000, so capped_basic = 12500
        epf = _compute_pf(
            basic_annual=Decimal("150000"),
            employee_contribution_pct=Decimal("12"),
            employer_contribution_pct=Decimal("12"),
            cap=Decimal("15000"),
        )
        # 12500 * 0.12 = 1500
        assert epf.employee_pf == Decimal("1500")
        assert epf.employer_pf == Decimal("1500")
        assert epf.total == Decimal("3000")

    def test_pf_at_cap(self):
        """Test PF calculation when basic equals cap."""
        # Basic annual = 180000, monthly = 15000, cap = 15000
        # 15000 == 15000, so capped_basic = 15000
        epf = _compute_pf(
            basic_annual=Decimal("180000"),
            employee_contribution_pct=Decimal("12"),
            employer_contribution_pct=Decimal("12"),
            cap=Decimal("15000"),
        )
        # 15000 * 0.12 = 1800
        assert epf.employee_pf == Decimal("1800")
        assert epf.employer_pf == Decimal("1800")
        assert epf.total == Decimal("3600")

    def test_pf_above_cap(self):
        """Test PF calculation when basic exceeds cap."""
        # Basic annual = 240000, monthly = 20000, cap = 15000
        # 20000 > 15000, so capped_basic = 15000 (min ensures this)
        epf = _compute_pf(
            basic_annual=Decimal("240000"),
            employee_contribution_pct=Decimal("12"),
            employer_contribution_pct=Decimal("12"),
            cap=Decimal("15000"),
        )
        # Cap limits to 15000 * 0.12 = 1800
        assert epf.employee_pf == Decimal("1800")
        assert epf.employer_pf == Decimal("1800")
        assert epf.total == Decimal("3600")

    def test_pf_zero_salary(self):
        """Test PF with zero salary."""
        epf = _compute_pf(basic_annual=Decimal("0"))
        assert epf.employee_pf == Decimal("0")
        assert epf.employer_pf == Decimal("0")
        assert epf.total == Decimal("0")

    def test_pf_min_not_max_mutation(self):
        """
        Catch mutation: min() → max()

        If max() is used instead of min(), the result would NOT be capped.
        With basic_monthly=20000, cap=15000:
        - Correct (min): min(20000, 15000) = 15000
        - Mutant (max): max(20000, 15000) = 20000
        """
        epf_above_cap = _compute_pf(
            basic_annual=Decimal("240000"),  # monthly = 20000
            cap=Decimal("15000"),
        )
        # Should be capped at 15000
        assert epf_above_cap.employee_pf == Decimal("1800")
        assert epf_above_cap.employee_pf != Decimal("2400")

    def test_pf_different_contributions(self):
        """Test PF with different employee and employer contribution rates."""
        epf = _compute_pf(
            basic_annual=Decimal("180000"),
            employee_contribution_pct=Decimal("10"),
            employer_contribution_pct=Decimal("15"),
            cap=Decimal("15000"),
        )
        # 15000 * 0.10 = 1500, 15000 * 0.15 = 2250
        assert epf.employee_pf == Decimal("1500")
        assert epf.employer_pf == Decimal("2250")
        assert epf.total == Decimal("3750")

    def test_pf_rounding(self):
        """Test that PF amounts are rounded to whole rupees."""
        epf = _compute_pf(basic_annual=Decimal("123456"))
        # 123456 / 12 = 10288
        # 10288 * 0.12 = 1234.56 → should quantize to 1235 (rounding)
        assert epf.employee_pf == epf.employee_pf.quantize(Decimal("1"))

    def test_pf_invalid_basic_negative(self):
        """Test that negative basic salary raises error."""
        with pytest.raises(ValueError, match="basic_annual cannot be negative"):
            _compute_pf(basic_annual=Decimal("-100000"))

    def test_pf_invalid_contribution_percentage(self):
        """Test that invalid contribution percentages raise error."""
        with pytest.raises(ValueError, match="must be between 0 and 100"):
            _compute_pf(
                basic_annual=Decimal("100000"),
                employee_contribution_pct=Decimal("150"),
            )


# ============================================================================
# TDS Calculation Tests - FY Boundary Conditions
# ============================================================================

class TestComputeTDSFYBoundaries:
    """Tests for TDS calculation with FY boundary conditions."""

    def test_tds_april_start_of_fy(self):
        """Test TDS in April (month 1 of FY)."""
        # April 1, 2024: Start of FY
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_tds=Decimal("0"),
        )
        # Month of FY = (4 - 4) % 12 + 1 = 0 + 1 = 1
        # Months remaining = 12 - 1 + 1 = 12
        # Monthly TDS = (120000 - 0) / 12 = 10000
        assert tds == Decimal("10000")

    def test_tds_may_second_month(self):
        """Test TDS in May (month 2 of FY)."""
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 5, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_tds=Decimal("10000"),
        )
        # Month of FY = (5 - 4) % 12 + 1 = 1 + 1 = 2
        # Months remaining = 12 - 2 + 1 = 11
        # Monthly TDS = (120000 - 10000) / 11 = 10000
        assert tds == Decimal("10000")

    def test_tds_march_last_month(self):
        """Test TDS in March (month 12 of FY)."""
        # March is the last month of FY
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2025, 3, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_tds=Decimal("110000"),
        )
        # Month of FY = (3 - 4) % 12 + 1 = -1 % 12 + 1 = 11 + 1 = 12
        # Months remaining = 12 - 12 + 1 = 1
        # Monthly TDS = (120000 - 110000) / 1 = 10000
        assert tds == Decimal("10000")

    def test_tds_january_month_9(self):
        """Test TDS in January (month 10 of FY)."""
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2025, 1, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_tds=Decimal("90000"),
        )
        # Month of FY = (1 - 4) % 12 + 1 = -3 % 12 + 1 = 9 + 1 = 10
        # Months remaining = 12 - 10 + 1 = 3
        # Monthly TDS = (120000 - 90000) / 3 = 10000
        assert tds == Decimal("10000")

    def test_tds_fy_boundary_april_detection(self):
        """
        Catch mutation: month >= 4 → month > 4 or month <= 4

        April 1 should detect FY start correctly.
        If condition is month > 4 (wrong), April would be treated as previous FY.
        """
        # April 1 with month >= 4: correct detection
        tds_april = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # April should be month 1 of FY, so 12 months remaining
        assert tds_april == Decimal("10000")

        # March 31 should be treated as last month of previous FY
        tds_march = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 3, 31),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # March should be month 12 of FY, so 1 month remaining
        assert tds_march == Decimal("120000")

    def test_tds_month_of_fy_calculation(self):
        """
        Catch mutations in: (month - 4) % 12 + 1

        Test all months to ensure correct month_of_fy values.
        """
        test_cases = [
            (date(2024, 4, 1), 1),   # April = month 1 of FY
            (date(2024, 5, 1), 2),   # May = month 2
            (date(2024, 6, 1), 3),   # June = month 3
            (date(2024, 12, 1), 9),  # December = month 9
            (date(2025, 1, 1), 10),  # January = month 10
            (date(2025, 3, 1), 12),  # March = month 12
        ]

        for test_date, expected_month_of_fy in test_cases:
            # Month remaining should be 12 - month_of_fy + 1
            expected_months_remaining = 12 - expected_month_of_fy + 1

            tds = _compute_monthly_tds_with_bonus(
                current_date=test_date,
                gross_monthly=Decimal("100000"),
                total_tax=Decimal("120000"),
            )

            expected_tds = (Decimal("120000") / Decimal(expected_months_remaining)).quantize(
                Decimal("0.01")
            )
            assert tds == expected_tds

    def test_tds_never_negative(self):
        """Test that TDS is never negative even if ytd_tds exceeds total_tax."""
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("100000"),
            ytd_tds=Decimal("150000"),  # Already paid more than total_tax
        )
        # Should return 0, not negative
        assert tds == Decimal("0")

    def test_tds_with_ytd_bonus(self):
        """Test TDS calculation with YTD bonus (not directly used but included)."""
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_bonus=Decimal("50000"),
            ytd_tds=Decimal("0"),
        )
        # YTD bonus doesn't directly affect monthly TDS in this calculation
        # Monthly TDS = (120000 - 0) / 12 = 10000
        assert tds == Decimal("10000")


# ============================================================================
# TDS Calculation Tests - Mutation Detection (Boundary Conditions)
# ============================================================================

class TestComputeTDSMutationDetection:
    """Tests specifically designed to catch surviving mutations in boundary conditions."""

    def test_fy_start_boundary_april_is_inclusive(self):
        """
        Catch mutation: month >= 4 → month > 4

        April (month 4) MUST be treated as the start of FY.
        If mutated to >, April would incorrectly use previous year's FY start.
        """
        # Test April 1 vs April 30 (same FY)
        tds_april_1 = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        tds_april_30 = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 30),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # Both should be month 1 of FY, so both should calculate with 12 months remaining
        assert tds_april_1 == Decimal("10000")
        assert tds_april_30 == Decimal("10000")
        assert tds_april_1 == tds_april_30

    def test_fy_start_boundary_march_exclusive(self):
        """
        Catch mutation: month >= 4 → month > 4 or month <= 3

        March (month 3) must be treated as the LAST month of the PREVIOUS FY.
        """
        # March 1, 2024 is part of FY 2023-24, which ends on March 31
        tds_march_1 = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 3, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # Should be month 12 of FY (1 month remaining)
        assert tds_march_1 == Decimal("120000")

        # Verify it's different from April
        tds_april_1 = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # April is month 1 of next FY (12 months remaining)
        assert tds_april_1 == Decimal("10000")
        assert tds_march_1 != tds_april_1

    def test_month_of_fy_all_months_distinct(self):
        """
        Catch mutations in: (month - 4) % 12 + 1

        Each of the 12 months must produce different TDS values
        to ensure the formula is correct.
        """
        tds_values = {}
        for month in range(1, 13):
            tds = _compute_monthly_tds_with_bonus(
                current_date=date(2024, month, 1),
                gross_monthly=Decimal("100000"),
                total_tax=Decimal("120000"),
            )
            tds_values[month] = tds

        # All TDS values should be different (verify no collisions)
        # This catches if the formula produces duplicate month_of_fy values
        unique_tds = set(tds_values.values())
        assert len(unique_tds) == 12, f"Expected 12 unique TDS values, got {len(unique_tds)}"

        # Verify specific months have specific relationships
        # April (month 4) should have the smallest TDS (12 months remaining)
        assert tds_values[4] == Decimal("10000")
        # March (month 3) should have the largest TDS (1 month remaining)
        assert tds_values[3] == Decimal("120000")

    def test_month_of_fy_formula_april_equals_1(self):
        """
        Verify: (month - 4) % 12 + 1 for April = 1

        Catches mutation: (month - 4) % 12 + 1 → (month - 4) % 12
        """
        # April (month 4): (4 - 4) % 12 + 1 = 0 + 1 = 1
        # Should have 12 months remaining
        tds_april = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # 120000 / 12 = 10000
        assert tds_april == Decimal("10000")

    def test_month_of_fy_formula_march_equals_12(self):
        """
        Verify: (month - 4) % 12 + 1 for March = 12

        Catches mutation: (month - 4) % 12 + 1 → (month - 4) % 12
        """
        # March (month 3): (3 - 4) % 12 + 1 = -1 % 12 + 1 = 11 + 1 = 12
        # Should have 1 month remaining
        tds_march = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 3, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # 120000 / 1 = 120000
        assert tds_march == Decimal("120000")

    def test_months_remaining_formula_verification(self):
        """
        Verify: months_remaining = 12 - month_of_fy + 1

        Catches mutations like:
        - 12 - month_of_fy (missing +1)
        - 11 - month_of_fy + 1
        - 12 - month_of_fy - 1
        """
        test_cases = [
            (date(2024, 4, 1), 12),   # April: 12 - 1 + 1 = 12
            (date(2024, 5, 1), 11),   # May: 12 - 2 + 1 = 11
            (date(2024, 6, 1), 10),   # June: 12 - 3 + 1 = 10
            (date(2024, 7, 1), 9),    # July: 12 - 4 + 1 = 9
            (date(2024, 8, 1), 8),    # August: 12 - 5 + 1 = 8
            (date(2024, 9, 1), 7),    # September: 12 - 6 + 1 = 7
            (date(2024, 10, 1), 6),   # October: 12 - 7 + 1 = 6
            (date(2024, 11, 1), 5),   # November: 12 - 8 + 1 = 5
            (date(2024, 12, 1), 4),   # December: 12 - 9 + 1 = 4
            (date(2025, 1, 1), 3),    # January: 12 - 10 + 1 = 3
            (date(2025, 2, 1), 2),    # February: 12 - 11 + 1 = 2
            (date(2025, 3, 1), 1),    # March: 12 - 12 + 1 = 1
        ]

        for test_date, expected_months_remaining in test_cases:
            expected_tds = (Decimal("120000") / Decimal(expected_months_remaining)).quantize(
                Decimal("0.01")
            )
            tds = _compute_monthly_tds_with_bonus(
                current_date=test_date,
                gross_monthly=Decimal("100000"),
                total_tax=Decimal("120000"),
            )
            assert tds == expected_tds, (
                f"Failed for {test_date}: expected {expected_tds} "
                f"(months_remaining={expected_months_remaining}), got {tds}"
            )

    def test_quantize_rounding_precision(self):
        """
        Verify: .quantize(Decimal("0.01")) for proper rounding

        Catches mutation: .quantize(Decimal("0.01")) → .quantize(Decimal("1"))
        or missing quantize entirely.
        """
        # Create a case where rounding matters
        # 120000 / 11 = 10909.090909...
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 5, 1),  # May: 11 months remaining
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # Should be rounded to 2 decimal places
        assert tds == Decimal("10909.09")
        assert str(tds).count('.') == 1
        assert len(str(tds).split('.')[1]) == 2

    def test_quantize_rounds_down_correctly(self):
        """
        Verify quantize rounds correctly for .091 → .09
        """
        # 100000 / 11 = 9090.909090...
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 5, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("100000"),
        )
        assert tds == Decimal("9090.91")

    def test_max_constraint_prevents_negative(self):
        """
        Verify: max(Decimal("0"), monthly_tds)

        Catches mutation: max() → min() or missing max()
        """
        # Case where remaining_tax is negative
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("50000"),
            ytd_tds=Decimal("100000"),  # Already paid more than total_tax
        )
        # Should be 0, not negative
        assert tds == Decimal("0")
        assert tds >= Decimal("0")

    def test_max_constraint_with_zero_tax(self):
        """
        Verify max(0, ...) when total_tax is zero.
        """
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("0"),
            ytd_tds=Decimal("0"),
        )
        assert tds == Decimal("0")

    def test_bonus_parameter_not_used_in_calculation(self):
        """
        Verify that ytd_bonus parameter doesn't affect current month TDS.

        This is actually important to test because the parameter is received
        but not currently used in the calculation. If someone adds logic
        using it later, this test ensures it's intentional.
        """
        # Calculate with different bonus values
        tds_no_bonus = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_bonus=Decimal("0"),
        )

        tds_with_bonus = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_bonus=Decimal("50000"),
        )

        # Should be identical since bonus doesn't affect monthly TDS
        assert tds_no_bonus == tds_with_bonus == Decimal("10000")

    def test_ytd_tds_affects_remaining_tax(self):
        """
        Verify that ytd_tds correctly reduces remaining tax.

        Catches mutation: total_tax - ytd_tds → total_tax + ytd_tds
        or missing ytd_tds from calculation.
        """
        # With no YTD TDS
        tds_fresh = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_tds=Decimal("0"),
        )
        # 120000 / 12 = 10000
        assert tds_fresh == Decimal("10000")

        # With YTD TDS already paid
        tds_partial = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
            ytd_tds=Decimal("60000"),  # Half already paid
        )
        # (120000 - 60000) / 12 = 5000
        assert tds_partial == Decimal("5000")
        assert tds_partial == tds_fresh / 2

    def test_months_remaining_edge_case_december(self):
        """
        Catch off-by-one errors in months_remaining calculation.

        December should be month 9 of FY, with 4 months remaining
        (Dec, Jan, Feb, Mar).
        """
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 12, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # Month of FY = (12 - 4) % 12 + 1 = 8 + 1 = 9
        # Months remaining = 12 - 9 + 1 = 4
        # TDS = 120000 / 4 = 30000
        assert tds == Decimal("30000")

    def test_months_remaining_edge_case_january(self):
        """
        Catch off-by-one errors for January.

        January should be month 10 of FY, with 3 months remaining
        (Jan, Feb, Mar).
        """
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2025, 1, 1),
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),
        )
        # Month of FY = (1 - 4) % 12 + 1 = -3 % 12 + 1 = 9 + 1 = 10
        # Months remaining = 12 - 10 + 1 = 3
        # TDS = 120000 / 3 = 40000
        assert tds == Decimal("40000")

    def test_exact_tds_computation_no_rounding_loss(self):
        """
        Verify that TDS computation is exact where possible.

        Catches if quantize() or max() operations are misplaced.
        """
        # Perfect division case (no rounding needed)
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),  # 12 months remaining
            gross_monthly=Decimal("100000"),
            total_tax=Decimal("120000"),  # Divides evenly: 120000 / 12 = 10000
        )
        assert tds == Decimal("10000")
        assert tds == Decimal("10000.00")

    def test_tds_never_exceeds_total_tax(self):
        """
        Verify that monthly TDS never exceeds total_tax / months_remaining.
        """
        # Even in first month, TDS should be <= total_tax / 12
        tds = _compute_monthly_tds_with_bonus(
            current_date=date(2024, 4, 1),
            gross_monthly=Decimal("1000000"),  # Large salary
            total_tax=Decimal("120000"),
        )
        assert tds <= Decimal("120000") / Decimal("12")


# ============================================================================
# Transaction Recording Tests
# ============================================================================

class TestTransactionRecording:
    """Tests for transaction recording and validation."""

    def test_transaction_creation(self):
        """Test creating a transaction."""
        trans = Transaction(
            date=date(2024, 4, 1),
            category="salary_payment",
            amount=Decimal("50000"),
            description="Salary Payment",
        )
        assert trans.date == date(2024, 4, 1)
        assert trans.category == "salary_payment"
        assert trans.amount == Decimal("50000")

    def test_transaction_invalid_category(self):
        """Test that invalid categories raise error."""
        with pytest.raises(ValueError, match="Invalid category"):
            Transaction(
                date=date(2024, 4, 1),
                category="invalid",
                amount=Decimal("50000"),
                description="Test",
            )

    def test_transaction_negative_amount(self):
        """Test that negative amounts raise error."""
        with pytest.raises(ValueError, match="Amount cannot be negative"):
            Transaction(
                date=date(2024, 4, 1),
                category="salary_payment",
                amount=Decimal("-50000"),
                description="Test",
            )

    def test_epf_transaction_category(self):
        """Test that EPF transaction has correct category."""
        trans = Transaction(
            date=date(2024, 4, 1),
            category="epf_contribution",
            amount=Decimal("3600"),
            description="EPF Contribution",
        )
        assert trans.category == "epf_contribution"

    def test_tds_transaction_category(self):
        """Test that TDS transaction has correct category."""
        trans = Transaction(
            date=date(2024, 4, 1),
            category="tds_payment",
            amount=Decimal("10000"),
            description="TDS Payment",
            source_product_id="product-123",
        )
        assert trans.category == "tds_payment"
        assert trans.source_product_id == "product-123"

    def test_salary_transaction_category(self):
        """Test that salary transaction has correct category."""
        trans = Transaction(
            date=date(2024, 4, 1),
            category="salary_payment",
            amount=Decimal("86400"),
            description="Salary Payment",
        )
        assert trans.category == "salary_payment"


# ============================================================================
# Salary State Tests
# ============================================================================

class TestSalaryState:
    """Tests for salary state management."""

    def test_salary_state_creation(self):
        """Test creating a salary state."""
        state = SalaryState(
            employee_id="EMP001",
            current_month=date(2024, 4, 1),
            gross_salary=Decimal("100000"),
        )
        assert state.employee_id == "EMP001"
        assert state.current_month == date(2024, 4, 1)
        assert state.gross_salary == Decimal("100000")
        assert state.current_monthly == Decimal("0")

    def test_salary_state_current_monthly_update(self):
        """Test that current_monthly represents net salary."""
        state = SalaryState(
            employee_id="EMP001",
            current_month=date(2024, 4, 1),
            current_monthly=Decimal("86400"),
        )
        assert state.current_monthly == Decimal("86400")

    def test_add_transaction_to_state(self):
        """Test adding transactions to salary state."""
        state = SalaryState(employee_id="EMP001", current_month=date(2024, 4, 1))
        trans = Transaction(
            date=date(2024, 4, 1),
            category="salary_payment",
            amount=Decimal("86400"),
            description="Salary",
        )
        state.add_transaction(trans)
        assert len(state.transactions) == 1
        assert state.transactions[0] == trans

    def test_multiple_transactions_in_state(self):
        """Test adding multiple transactions to state."""
        state = SalaryState(employee_id="EMP001", current_month=date(2024, 4, 1))

        trans1 = Transaction(
            date=date(2024, 4, 1),
            category="epf_contribution",
            amount=Decimal("3600"),
            description="EPF",
        )
        trans2 = Transaction(
            date=date(2024, 4, 1),
            category="tds_payment",
            amount=Decimal("10000"),
            description="TDS",
        )
        trans3 = Transaction(
            date=date(2024, 4, 1),
            category="salary_payment",
            amount=Decimal("86400"),
            description="Salary",
        )

        state.add_transaction(trans1)
        state.add_transaction(trans2)
        state.add_transaction(trans3)

        assert len(state.transactions) == 3
        assert state.transactions[0].category == "epf_contribution"
        assert state.transactions[1].category == "tds_payment"
        assert state.transactions[2].category == "salary_payment"

    def test_add_invalid_transaction_type(self):
        """Test that adding non-Transaction object raises error."""
        state = SalaryState(employee_id="EMP001", current_month=date(2024, 4, 1))
        with pytest.raises(TypeError):
            state.add_transaction({"date": date(2024, 4, 1)})


# ============================================================================
# Employer Integration Tests
# ============================================================================

class TestEmployerSimulateDay:
    """Tests for employer simulate_day method."""

    def test_simulate_day_basic(self):
        """Test basic day simulation."""
        employer = Employer()
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
        )

        # Verify PF calculation (capped at 15000, so 15000 * 0.12 = 1800)
        assert result["pf"]["employee"] == Decimal("1800")
        assert result["pf"]["employer"] == Decimal("1800")
        assert result["pf"]["total"] == Decimal("3600")

        # Verify TDS calculation (April = month 1 of FY, 12 months remaining)
        assert result["tds"] == Decimal("10000")

        # Verify net salary (100000 - 1800 - 10000 = 88200)
        assert result["net_salary"] == Decimal("88200.00")

    def test_simulate_day_epf_amount_accuracy(self):
        """
        Test that EPF contribution equals employee_pf + employer_pf.

        Catches mutations in EPF amount calculation.
        """
        employer = Employer()
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("150000"),
            basic_annual=Decimal("1800000"),
            total_tax=Decimal("150000"),
        )

        # EPF total should equal employee + employer
        pf = result["pf"]
        assert pf["total"] == pf["employee"] + pf["employer"]

        # Verify transaction amount
        epf_trans = [t for t in result["transactions"] if t.category == "epf_contribution"][0]
        assert epf_trans.amount == pf["total"]

    def test_simulate_day_tds_payment_recorded(self):
        """Test that TDS payment is recorded as transaction."""
        employer = Employer()
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
        )

        tds_trans = [t for t in result["transactions"] if t.category == "tds_payment"]
        assert len(tds_trans) == 1
        assert tds_trans[0].amount == Decimal("10000")

    def test_simulate_day_salary_reflects_net(self):
        """Test that salary state reflects net salary."""
        employer = Employer()
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
        )

        state = result["employee_state"]
        # Net salary = 100000 - 1800 - 10000 = 88200
        assert state.current_monthly == Decimal("88200.00")

    def test_simulate_day_multiple_months(self):
        """Test simulating multiple months records all transactions."""
        employer = Employer()

        # April
        result_apr = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
        )

        # May (with YTD TDS from April)
        state = result_apr["employee_state"]
        result_may = employer.simulate_day(
            day=date(2024, 5, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
        )

        # Both should have recorded transactions
        assert len(state.transactions) >= 3  # EPF, TDS, Salary
        state_may = result_may["employee_state"]
        assert len(state_may.transactions) >= 6  # Both months

    def test_simulate_day_state_consistency(self):
        """Test that state ledger is consistent."""
        employer = Employer()
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
            product_id="PRODUCT001",
        )

        state = result["employee_state"]
        product_state = result["product_state"]

        # Verify all transactions are recorded
        assert len(state.transactions) == 3  # EPF, TDS, Salary

        # Verify transaction categories
        categories = {t.category for t in state.transactions}
        assert categories == {"epf_contribution", "tds_payment", "salary_payment"}

    def test_simulate_day_transaction_descriptions(self):
        """Test that transactions have proper descriptions."""
        employer = Employer()
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
        )

        for trans in result["transactions"]:
            assert isinstance(trans.description, str)
            assert len(trans.description) > 0

    def test_simulate_day_pf_cap_respected(self):
        """Test that PF cap is respected in simulation."""
        employer = Employer()
        # High salary to test cap
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("200000"),
            basic_annual=Decimal("2400000"),
            total_tax=Decimal("300000"),
        )

        # PF should be capped at 15000 monthly (12% of 15000 cap)
        # 15000 * 0.12 = 1800 per contribution
        assert result["pf"]["employee"] == Decimal("1800")
        assert result["pf"]["employer"] == Decimal("1800")

    def test_simulate_day_fy_boundary(self):
        """Test day simulation at FY boundary (April 1)."""
        employer = Employer()

        # Simulate on April 1 (first day of FY)
        result = employer.simulate_day(
            day=date(2024, 4, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("100000"),
            basic_annual=Decimal("1200000"),
            total_tax=Decimal("120000"),
        )

        # Should have 12 months remaining
        # TDS = 120000 / 12 = 10000
        assert result["tds"] == Decimal("10000")

    def test_simulate_day_march_last_month(self):
        """Test day simulation in March (last month of FY)."""
        employer = Employer()

        # Simulate on March 1 (last month of FY)
        # Use high salary and low tax to avoid negative net salary
        result = employer.simulate_day(
            day=date(2025, 3, 1),
            employee_id="EMP001",
            gross_monthly=Decimal("500000"),
            basic_annual=Decimal("6000000"),
            total_tax=Decimal("120000"),
        )

        # Should have 1 month remaining (March is month 12 of FY)
        # Month of FY = (3 - 4) % 12 + 1 = 12
        # Months remaining = 12 - 12 + 1 = 1
        # TDS = 120000 / 1 = 120000
        assert result["tds"] == Decimal("120000")
        # Net salary = 500000 - PF - 120000
        # PF = min(500000/12, 15000) * 0.12 = 15000 * 0.12 = 1800
        # Net = 500000 - 1800 - 120000 = 378200
        assert result["net_salary"] == Decimal("378200.00")


# ============================================================================
# EPF Data Class Tests
# ============================================================================

class TestEPFContribution:
    """Tests for EPFContribution dataclass."""

    def test_epf_creation(self):
        """Test creating EPF contribution."""
        epf = EPFContribution(
            employee_pf=Decimal("1800"),
            employer_pf=Decimal("1800"),
        )
        assert epf.employee_pf == Decimal("1800")
        assert epf.employer_pf == Decimal("1800")
        assert epf.total == Decimal("3600")

    def test_epf_total_calculation(self):
        """Test that total is calculated correctly."""
        epf = EPFContribution(
            employee_pf=Decimal("1500"),
            employer_pf=Decimal("2250"),
        )
        assert epf.total == Decimal("3750")
        assert epf.total == epf.employee_pf + epf.employer_pf

    def test_epf_zero_contributions(self):
        """Test EPF with zero contributions."""
        epf = EPFContribution(
            employee_pf=Decimal("0"),
            employer_pf=Decimal("0"),
        )
        assert epf.total == Decimal("0")
