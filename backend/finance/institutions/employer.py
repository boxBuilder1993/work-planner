"""
Employer salary processing and financial calculations.

This module handles:
- PF (Provident Fund) calculations for employees
- TDS (Tax Deducted at Source) calculations
- Salary state management
- Transaction recording for payroll
- Tax refund calculation and processing
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union

from backend.finance.products.tax_refund import TaxRefundConfig, TaxRefundState
from backend.finance.products.espp import (
    ESPPConfig,
    ESPPProduct,
    ESPPState,
    PurchaseDateSchedule,
)
from backend.finance.products.stock import StockState
from backend.finance.core.product import ProductType
from backend.finance.tax import compute_annual_tax


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Transaction:
    """Represents a financial transaction."""

    date: date
    category: str  # "salary_payment", "epf_contribution", "tds_payment", "refund_credit"
    amount: Decimal
    description: str
    source_product_id: Optional[str] = None

    def __post_init__(self):
        """Validate transaction after initialization."""
        valid_categories = ("salary_payment", "epf_contribution", "tds_payment", "refund_credit")
        if self.category not in valid_categories:
            raise ValueError(f"Invalid category: {self.category}")
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")


@dataclass
class EPFContribution:
    """Represents EPF contribution details."""

    employee_pf: Decimal
    employer_pf: Decimal
    total: Decimal = field(init=False)

    def __post_init__(self):
        """Calculate total PF contribution."""
        self.total = self.employee_pf + self.employer_pf


@dataclass
class SalaryState:
    """Represents the state of salary processing for an employee."""

    employee_id: str
    current_month: date  # First day of the month
    gross_salary: Decimal = Decimal("0")
    current_monthly: Decimal = Decimal("0")  # Net salary after deductions
    employee_pf: Decimal = Decimal("0")
    employer_pf: Decimal = Decimal("0")
    tds_paid: Decimal = Decimal("0")
    tds_paid_in_fy: Decimal = Decimal("0")  # Cumulative TDS paid in current FY
    fy_start: Optional[date] = None  # Start of current FY for TDS tracking
    transactions: List[Transaction] = field(default_factory=list)

    def add_transaction(self, transaction: Transaction) -> None:
        """Add a transaction to the salary state."""
        if not isinstance(transaction, Transaction):
            raise TypeError("transaction must be a Transaction instance")
        self.transactions.append(transaction)


@dataclass
class ProductState:
    """Represents the state of a product (salary account)."""

    product_id: str
    balance: Decimal = Decimal("0")
    ledger: Dict[str, Decimal] = field(default_factory=dict)


# ============================================================================
# PF Calculation
# ============================================================================

def _compute_pf(
    basic_annual: Decimal,
    employee_contribution_pct: Decimal = Decimal("12"),
    employer_contribution_pct: Decimal = Decimal("12"),
    cap: Decimal = Decimal("15000"),
) -> EPFContribution:
    """
    Compute PF (Provident Fund) contribution for an employee.

    Formula:
    - Basic monthly = basic_annual / 12
    - Capped basic = min(basic_monthly, cap)
    - Employee PF = capped_basic * (employee_contribution_pct / 100)
    - Employer PF = capped_basic * (employer_contribution_pct / 100)

    Args:
        basic_annual: Annual basic salary
        employee_contribution_pct: Employee PF contribution percentage (default 12%)
        employer_contribution_pct: Employer PF contribution percentage (default 12%)
        cap: Maximum salary cap for PF calculation (default 15000)

    Returns:
        EPFContribution with employee and employer PF amounts

    Raises:
        ValueError: If basic_annual < 0 or percentages are not 0-100
    """
    if basic_annual < 0:
        raise ValueError("basic_annual cannot be negative")
    if employee_contribution_pct < 0 or employee_contribution_pct > 100:
        raise ValueError("employee_contribution_pct must be between 0 and 100")
    if employer_contribution_pct < 0 or employer_contribution_pct > 100:
        raise ValueError("employer_contribution_pct must be between 0 and 100")

    # Calculate basic monthly
    basic_monthly = basic_annual / Decimal("12")

    # Apply cap - use min() to ensure we don't exceed the cap
    capped_basic = min(basic_monthly, cap)

    # Calculate PF contributions
    employee_rate = employee_contribution_pct / Decimal("100")
    employer_rate = employer_contribution_pct / Decimal("100")

    employee_pf = (capped_basic * employee_rate).quantize(Decimal("1"))
    employer_pf = (capped_basic * employer_rate).quantize(Decimal("1"))

    return EPFContribution(employee_pf=employee_pf, employer_pf=employer_pf)


# ============================================================================
# TDS Calculation
# ============================================================================

def _compute_monthly_tds_with_bonus(
    current_date: date,
    gross_monthly: Decimal,
    total_tax: Decimal,
    ytd_bonus: Decimal = Decimal("0"),
    ytd_tds: Decimal = Decimal("0"),
) -> Decimal:
    """
    Compute monthly TDS (Tax Deducted at Source) considering FY boundaries.

    Financial Year in India: April 1 to March 31

    Formula:
    - FY Start: April 1 if month >= 4, else previous year April 1
    - Month of FY: (month - 4) % 12 + 1 (April=1, May=2, ..., March=12)
    - Months remaining: 12 - month_of_fy + 1
    - Projected annual: gross_monthly * 12 + ytd_bonus
    - Monthly TDS: max(0, (total_tax - ytd_tds) / months_remaining)

    Args:
        current_date: Current date
        gross_monthly: Monthly gross salary
        total_tax: Total estimated tax for the FY
        ytd_bonus: Year-to-date bonus received
        ytd_tds: Year-to-date TDS already paid

    Returns:
        Monthly TDS amount as Decimal

    Raises:
        ValueError: If gross_monthly < 0, total_tax < 0, or dates are invalid
    """
    if gross_monthly < 0:
        raise ValueError("gross_monthly cannot be negative")
    if total_tax < 0:
        raise ValueError("total_tax cannot be negative")
    if ytd_bonus < 0:
        raise ValueError("ytd_bonus cannot be negative")
    if ytd_tds < 0:
        raise ValueError("ytd_tds cannot be negative")

    # Determine if we're in the current FY or need to look back to previous year
    # FY starts on April 1, so if month >= 4, we're in the current FY
    if current_date.month >= 4:
        fy_start = date(current_date.year, 4, 1)
    else:
        fy_start = date(current_date.year - 1, 4, 1)

    # Calculate month of FY (April=1, May=2, ..., March=12)
    month_of_fy = (current_date.month - 4) % 12 + 1

    # Months remaining in FY including current month
    months_remaining = 12 - month_of_fy + 1

    # Calculate projected annual income
    projected_annual = gross_monthly * Decimal("12") + ytd_bonus

    # Calculate remaining tax
    remaining_tax = total_tax - ytd_tds

    # Monthly TDS: distribute remaining tax over remaining months
    if months_remaining <= 0:
        return Decimal("0")

    monthly_tds = (remaining_tax / Decimal(months_remaining)).quantize(Decimal("0.01"))

    # Never return negative TDS
    return max(Decimal("0"), monthly_tds)


# ============================================================================
# Employer Class
# ============================================================================

class Employer:
    """
    Handles salary processing and financial transactions for employees.
    """

    def __init__(
        self,
        nps_products: Optional[Dict] = None,
        tax_refund_products: Optional[Dict] = None,
        espp_products: Optional[List[ESPPProduct]] = None,
        stock_states: Optional[Dict[str, StockState]] = None,
    ):
        """
        Initialize employer.

        Args:
            nps_products: Optional dictionary of NPS products by employee_id
            tax_refund_products: Optional dictionary of tax refund products by salary_id
            espp_products: Optional list of ESPP products linked to salaries
            stock_states: Optional dictionary of StockState by stock_id for ESPP share purchases
        """
        self.employee_states: Dict[str, SalaryState] = {}
        self.product_states: Dict[str, ProductState] = {}
        self.nps_products: Dict[str, any] = nps_products or {}  # NPS products by employee_id
        self.tax_refund_products: Dict[str, any] = tax_refund_products or {}  # Tax refund products by salary_id
        self.espp_products: List[ESPPProduct] = espp_products or []  # ESPP products linked to salaries
        self.stock_states: Dict[str, StockState] = stock_states or {}  # Stock states for ESPP share purchases
        self.refund_states: Dict[str, TaxRefundState] = {}  # Track refund states by tax_refund_id
        self.espp_states: Dict[str, ESPPState] = {}  # Track ESPP states by espp_id

    def _get_fy_dates(self, current_date: date) -> Tuple[date, date]:
        """
        Get the start and end dates of the financial year for a given date.

        Financial Year in India: April 1 to March 31

        Args:
            current_date: Any date within the FY

        Returns:
            Tuple of (fy_start, fy_end) where fy_start is April 1 and fy_end is March 31
        """
        if current_date.month >= 4:
            # Current calendar year's April to next year's March
            fy_start = date(current_date.year, 4, 1)
            fy_end = date(current_date.year + 1, 3, 31)
        else:
            # Previous calendar year's April to current year's March
            fy_start = date(current_date.year - 1, 4, 1)
            fy_end = date(current_date.year, 3, 31)
        return fy_start, fy_end

    def _find_tax_refund_for_salary(
        self,
        salary_id: str,
    ) -> Optional[Tuple[TaxRefundConfig, str]]:
        """
        Find TaxRefundConfig linked to a salary product.

        Args:
            salary_id: The salary product ID

        Returns:
            Tuple of (TaxRefundConfig, tax_refund_id) if found, None otherwise
        """
        for tax_refund_id, tax_refund_product in self.tax_refund_products.items():
            if hasattr(tax_refund_product, "config"):
                config = tax_refund_product.config
            else:
                config = tax_refund_product

            if config.salary_id == salary_id:
                return (config, tax_refund_id)

        return None

    def _find_espp_for_salary(self, salary_id: str) -> List[ESPPProduct]:
        """
        Find all ESPP products linked to a given salary.

        Args:
            salary_id: The salary product ID

        Returns:
            List of ESPPProduct instances linked to the salary
        """
        return [espp for espp in self.espp_products if espp.config.salary_id == salary_id]

    def _is_purchase_date(
        self, d: date, purchase_dates: List[PurchaseDateSchedule]
    ) -> bool:
        """
        Check if a given date matches any purchase date schedule.

        Args:
            d: The date to check
            purchase_dates: List of purchase date schedules with {month, day}

        Returns:
            True if the date matches any purchase schedule, False otherwise
        """
        for schedule in purchase_dates:
            # Handle edge cases like Feb 31 by checking if the day is valid for the month
            if d.month == schedule.month:
                # For Feb 31 or other invalid dates, the schedule is skipped for that month
                if d.day == schedule.day:
                    return True
        return False

    def set_stock_state(self, stock_id: str, state: StockState) -> None:
        """
        Set or update stock state for ESPP share purchases.

        This method allows external institutions (e.g., StockInstitution) to
        provide current stock states so ESPP can calculate share purchases.

        Args:
            stock_id: Stock product ID
            state: Current StockState with up-to-date price and share count

        Raises:
            ValueError: If state is None or state.id doesn't match stock_id
        """
        if state is None:
            raise ValueError("state cannot be None")
        if state.id != stock_id:
            raise ValueError(f"state.id ({state.id}) must match stock_id ({stock_id})")

        self.stock_states[stock_id] = state

    def get_stock_state(self, stock_id: str) -> Optional[StockState]:
        """
        Get current stock state.

        Args:
            stock_id: Stock product ID

        Returns:
            Current StockState if available, None otherwise
        """
        return self.stock_states.get(stock_id)

    def simulate_day(
        self,
        day: date,
        employee_id: str,
        gross_monthly: Decimal,
        basic_annual: Decimal,
        total_tax: Decimal,
        salary_id: Optional[str] = None,
        product_id: Optional[str] = None,
        deduction_80c: Decimal = Decimal("0"),
        deduction_80d: Decimal = Decimal("0"),
        hra_exemption: Decimal = Decimal("0"),
        tax_regime: str = "old",
    ) -> Dict[str, any]:
        """
        Simulate a day of salary processing and record transactions.

        This function:
        1. Calculates PF contribution (employee + employer)
        2. Calculates TDS deduction
        3. Calculates net salary (gross - employee_pf - tds)
        4. Records EPF, TDS, and salary transactions
        5. Updates employee and product states
        6. Handles tax refund calculation at FY boundary (March 31 → April 1)
        7. Processes refund credits on scheduled dates

        Args:
            day: The date being simulated
            employee_id: Employee ID
            gross_monthly: Monthly gross salary
            basic_annual: Annual basic salary for PF calculation
            total_tax: Total estimated tax for the FY
            salary_id: Optional salary product ID for linking transactions
            product_id: Optional product ID for state tracking
            deduction_80c: Annual 80C deduction for tax refund calculation
            deduction_80d: Annual 80D deduction for tax refund calculation
            hra_exemption: Annual HRA exemption for tax refund calculation
            tax_regime: Tax regime ("old" or "new") for refund calculation

        Returns:
            Dictionary with transaction records and state updates
        """
        # Initialize or retrieve employee state
        if employee_id not in self.employee_states:
            first_of_month = day.replace(day=1)
            fy_start, _ = self._get_fy_dates(day)
            self.employee_states[employee_id] = SalaryState(
                employee_id=employee_id,
                current_month=first_of_month,
                gross_salary=gross_monthly,
                fy_start=fy_start,
            )

        state = self.employee_states[employee_id]

        # Update gross salary
        state.gross_salary = gross_monthly

        # Initialize FY tracking if needed
        if state.fy_start is None:
            fy_start, _ = self._get_fy_dates(day)
            state.fy_start = fy_start

        # Calculate PF contribution
        pf_contrib = _compute_pf(
            basic_annual=basic_annual,
            employee_contribution_pct=Decimal("12"),
            employer_contribution_pct=Decimal("12"),
        )

        state.employee_pf = pf_contrib.employee_pf
        state.employer_pf = pf_contrib.employer_pf

        # Calculate TDS
        monthly_tds = _compute_monthly_tds_with_bonus(
            current_date=day,
            gross_monthly=gross_monthly,
            total_tax=total_tax,
            ytd_tds=state.tds_paid_in_fy,
        )

        state.tds_paid = monthly_tds

        # Accumulate TDS in current FY
        state.tds_paid_in_fy += monthly_tds

        # Calculate net salary
        net_salary = gross_monthly - pf_contrib.employee_pf - monthly_tds
        net_salary = net_salary.quantize(Decimal("0.01"))

        state.current_monthly = net_salary

        # Create transactions
        transactions = []

        # EPF transaction
        epf_description = f"EPF Contribution - Employee: {pf_contrib.employee_pf}, Employer: {pf_contrib.employer_pf}"
        epf_transaction = Transaction(
            date=day,
            category="epf_contribution",
            amount=pf_contrib.total,
            description=epf_description,
            source_product_id=salary_id,
        )
        transactions.append(epf_transaction)
        state.add_transaction(epf_transaction)

        # TDS transaction
        if monthly_tds > 0:
            tds_description = f"TDS Payment - {monthly_tds}"
            tds_transaction = Transaction(
                date=day,
                category="tds_payment",
                amount=monthly_tds,
                description=tds_description,
                source_product_id=product_id or salary_id,
            )
            transactions.append(tds_transaction)
            state.add_transaction(tds_transaction)

        # Handle ESPP contributions (deduct from net salary and add to cash pool)
        espp_contributions = self._process_espp_contributions(
            day=day,
            salary_id=salary_id,
            gross_monthly=gross_monthly,
        )
        net_salary -= espp_contributions["total_deduction"]
        net_salary = net_salary.quantize(Decimal("0.01"))
        transactions.extend(espp_contributions["transactions"])

        # Salary transaction
        salary_description = f"Salary Payment - Net: {net_salary}"
        salary_transaction = Transaction(
            date=day,
            category="salary_payment",
            amount=net_salary,
            description=salary_description,
            source_product_id=product_id or salary_id,
        )
        transactions.append(salary_transaction)
        state.add_transaction(salary_transaction)

        # Update or create product state
        if product_id:
            if product_id not in self.product_states:
                self.product_states[product_id] = ProductState(product_id=product_id)

            prod_state = self.product_states[product_id]

            # Update ledger
            if day not in prod_state.ledger:
                prod_state.ledger[str(day)] = Decimal("0")

            prod_state.ledger[str(day)] += net_salary
            prod_state.balance += net_salary

        # Handle FY boundary for tax refund calculation
        refund_transactions = self._handle_fy_boundary_and_refunds(
            day=day,
            employee_id=employee_id,
            salary_id=salary_id,
            product_id=product_id,
            basic_annual=basic_annual,
            deduction_80c=deduction_80c,
            deduction_80d=deduction_80d,
            hra_exemption=hra_exemption,
            tax_regime=tax_regime,
        )

        transactions.extend(refund_transactions)

        # Handle ESPP purchase on purchase dates
        espp_purchase_transactions = self._process_espp_purchases(day=day)
        transactions.extend(espp_purchase_transactions)

        return {
            "employee_state": state,
            "transactions": transactions,
            "product_state": self.product_states.get(product_id),
            "pf": {
                "employee": pf_contrib.employee_pf,
                "employer": pf_contrib.employer_pf,
                "total": pf_contrib.total,
            },
            "tds": monthly_tds,
            "net_salary": net_salary,
        }

    def _handle_fy_boundary_and_refunds(
        self,
        day: date,
        employee_id: str,
        salary_id: Optional[str],
        product_id: Optional[str],
        basic_annual: Decimal,
        deduction_80c: Decimal,
        deduction_80d: Decimal,
        hra_exemption: Decimal,
        tax_regime: str,
    ) -> List[Transaction]:
        """
        Handle tax refund calculation at FY boundary and process refund credits.

        This method:
        1. Detects FY boundary (March 31 → April 1)
        2. Calculates annual tax liability using all deductions and regime
        3. Computes refund = max(0, tds_paid - liability)
        4. Schedules refund credit for refund_lag_days later
        5. Processes refund credits on their scheduled dates
        6. Creates BANK_ACCOUNT transactions for credited refunds
        7. Updates TaxRefundState

        Args:
            day: Current date being simulated
            employee_id: Employee ID
            salary_id: Salary product ID
            product_id: Product ID for transactions
            basic_annual: Annual basic salary for tax calculation
            deduction_80c: Annual 80C deduction
            deduction_80d: Annual 80D deduction
            hra_exemption: Annual HRA exemption
            tax_regime: Tax regime ("old" or "new")

        Returns:
            List of refund-related transactions
        """
        transactions = []

        # Get or find tax refund configuration
        tax_refund_result = self._find_tax_refund_for_salary(salary_id) if salary_id else None
        if not tax_refund_result:
            return transactions

        tax_refund_config, tax_refund_id = tax_refund_result
        state = self.employee_states[employee_id]

        # Check if we're transitioning to a new FY (April 1)
        # This means the previous day was March 31
        previous_day = day - timedelta(days=1)
        is_fy_boundary = (previous_day.month == 3 and previous_day.day == 31 and
                          day.month == 4 and day.day == 1)

        # Initialize refund state if needed
        if tax_refund_id not in self.refund_states:
            self.refund_states[tax_refund_id] = TaxRefundState(
                id=tax_refund_id,
                product_type=ProductType.TAX_REFUND,
                date=day,
            )

        refund_state = self.refund_states[tax_refund_id]

        # At FY boundary (March 31 → April 1)
        # Only process if we're transitioning FROM a previous FY, not the first simulation day
        is_transitioning_fy = False
        if is_fy_boundary and state.fy_start:
            # Check if state.fy_start is from a previous FY (not the current FY)
            current_fy_start, _ = self._get_fy_dates(day)
            is_transitioning_fy = state.fy_start < current_fy_start

        if is_transitioning_fy:
            # Get FY dates for the completed FY
            fy_start = state.fy_start
            fy_end = date(fy_start.year + 1, 3, 31)

            # Calculate annual tax liability using compute_annual_tax
            gross_annual = basic_annual
            annual_tax_liability = compute_annual_tax(
                gross_annual=gross_annual,
                deduction_80c=deduction_80c,
                deduction_80d=deduction_80d,
                hra_exemption=hra_exemption,
                regime=tax_regime,
            )

            # Calculate refund
            tds_paid_in_completed_fy = state.tds_paid_in_fy
            refund_amount = max(Decimal("0"), tds_paid_in_completed_fy - annual_tax_liability)

            # Update refund state with FY calculations
            refund_state.update_fy_calculations(
                fy_start=fy_start,
                fy_end=fy_end,
                tds_paid=tds_paid_in_completed_fy,
                annual_liability=annual_tax_liability,
            )

            # If refund > 0, schedule credit for refund_lag_days later
            if refund_amount > Decimal("0"):
                refund_credit_date = day + timedelta(days=tax_refund_config.refund_lag_days)
                refund_state.schedule_refund(refund_amount, refund_credit_date)

            # Reset TDS paid for new FY
            state.tds_paid_in_fy = Decimal("0")
            state.fy_start, _ = self._get_fy_dates(day)

        # Check if today is a scheduled refund credit date
        if (refund_state.refund_scheduled_date and
            day == refund_state.refund_scheduled_date and
            refund_state.status == "scheduled"):

            # Create BANK_ACCOUNT transaction for refund credit
            refund_description = (
                f"Tax Refund Credit - FY {refund_state.fy_start.year}-"
                f"{refund_state.fy_end.year if refund_state.fy_end else 'N/A'} - "
                f"TDS Paid: {refund_state.tds_paid_in_fy}, "
                f"Liability: {refund_state.annual_tax_liability}"
            )
            refund_transaction = Transaction(
                date=day,
                category="refund_credit",
                amount=refund_state.refund_amount,
                description=refund_description,
                source_product_id=tax_refund_config.bank_account_id,
            )
            transactions.append(refund_transaction)
            state.add_transaction(refund_transaction)

            # Update refund state to "credited"
            refund_state.credit_refund(day)

        return transactions

    def _process_espp_contributions(
        self,
        day: date,
        salary_id: Optional[str],
        gross_monthly: Decimal,
    ) -> Dict[str, any]:
        """
        Process ESPP contributions on salary day.

        This method:
        1. Checks if today is a salary day (1st of month by default)
        2. Finds all ESPP products linked to the salary
        3. For each active ESPP, calculates contribution based on contribution_pct
        4. Adds contribution to ESPP cash_pool
        5. Returns the total deduction to reduce net_salary

        Args:
            day: Current date being simulated
            salary_id: Salary product ID
            gross_monthly: Monthly gross salary

        Returns:
            Dictionary with:
                - total_deduction: Total amount deducted for ESPP contributions
                - transactions: List of ESPP-related transactions
        """
        total_deduction = Decimal("0")
        transactions = []

        if not salary_id:
            return {"total_deduction": total_deduction, "transactions": transactions}

        # Only process contributions on salary day (1st of month)
        if day.day != 1:
            return {"total_deduction": total_deduction, "transactions": transactions}

        # Find all ESPP products linked to this salary
        espp_list = self._find_espp_for_salary(salary_id)

        for espp in espp_list:
            # Check if ESPP is active
            if not espp.is_active(day):
                continue

            # Get or initialize ESPP state
            if espp.config.id not in self.espp_states:
                self.espp_states[espp.config.id] = ESPPState(
                    id=espp.config.id,
                    product_type=ProductType.ESPP,
                    date=day,
                    cash_pool=Decimal("0"),
                    total_shares_purchased=Decimal("0"),
                )

            espp_state = self.espp_states[espp.config.id]
            espp_state.date = day

            # Calculate contribution: contribution_pct × gross_monthly
            contribution_pct = espp.config.contribution_pct.resolve(day)
            contribution_amount = (gross_monthly * contribution_pct / Decimal("100")).quantize(
                Decimal("0.01")
            )

            if contribution_amount > Decimal("0"):
                # Add to ESPP cash pool
                espp_state.add_contribution(contribution_amount)
                total_deduction += contribution_amount

                # Create transaction record
                espp_description = (
                    f"ESPP Contribution - {contribution_pct}% of gross salary "
                    f"(₹{contribution_amount})"
                )
                # Note: We don't create a formal transaction here as the deduction
                # is reflected in the reduced net_salary

        return {"total_deduction": total_deduction, "transactions": transactions}

    def _process_espp_purchases(self, day: date) -> List[Transaction]:
        """
        Process ESPP purchases on scheduled purchase dates.

        This method:
        1. For each ESPP product, checks if today is a purchase date
        2. If yes, calculates shares to buy: cash_pool / (stock_price × (1 - discount))
        3. Updates ESPP state: resets cash_pool, increments total_shares_purchased
        4. Updates linked Stock holding with new shares

        Requires:
        - Stock states to be available in self.stock_states (populated by caller)
        - Stock must have current_price set

        Args:
            day: Current date being simulated

        Returns:
            List of purchase-related transactions
        """
        transactions = []

        for espp in self.espp_products:
            # Check if ESPP is active
            if not espp.is_active(day):
                continue

            # Get ESPP state
            if espp.config.id not in self.espp_states:
                continue  # ESPP state should have been initialized during contribution
            espp_state = self.espp_states[espp.config.id]

            # Check if today is a purchase date
            if not self._is_purchase_date(day, espp.config.purchase_dates):
                continue

            # Check if there's cash to purchase
            if espp_state.cash_pool <= Decimal("0"):
                continue

            # Get current stock price from stock_states
            stock_id = espp.config.stock_id
            if stock_id not in self.stock_states:
                # Linked stock state not found - log warning but continue
                continue

            stock_state = self.stock_states[stock_id]

            # Validate stock state has valid price
            if stock_state.current_price <= Decimal("0"):
                # No valid stock price available, skip purchase
                continue

            # Get discount: discount × stock_price
            discount_pct = espp.config.discount.resolve(day)
            discount_factor = Decimal("1") - (discount_pct / Decimal("100"))

            # Ensure discount_factor is positive and reasonable (discount < 100%)
            if discount_factor <= Decimal("0"):
                # Invalid discount, skip purchase
                continue

            # Calculate shares to buy: cash_pool / (stock_price × (1 - discount))
            effective_price = stock_state.current_price * discount_factor
            shares_to_buy = (espp_state.cash_pool / effective_price).quantize(Decimal("0.0001"))

            if shares_to_buy > Decimal("0"):
                # Update ESPP state
                espp_state.purchase_shares(shares_to_buy)
                cash_used = espp_state.cash_pool
                espp_state.debit_cash_pool(cash_used)

                # Update stock holding with new shares
                stock_state.add_shares(shares_to_buy)
                stock_state.date = day

                # Create transaction record (optional - for audit trail)
                purchase_description = (
                    f"ESPP Purchase - Bought {shares_to_buy} shares at "
                    f"₹{stock_state.current_price} with {discount_pct}% discount "
                    f"(Effective price: ₹{effective_price}, Cash used: ₹{cash_used})"
                )
                # Note: ESPP purchase is internal bookkeeping between ESPP and Stock holdings
                # Not a direct bank transaction, so we don't create a formal Transaction object

        return transactions
