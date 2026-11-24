from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from database import get_connection


# ============================================================
# 1. MONEY CONVERSION
# ============================================================

def rupees_to_paise(value):

    try:

        amount = Decimal(str(value))

    except (InvalidOperation, ValueError):

        raise ValueError("Enter a valid payment amount.")

    if not amount.is_finite():

        raise ValueError("Payment amount must be finite.")

    if amount <= 0:

        raise ValueError(
            "Payment amount must be greater than zero."
        )

    amount = amount.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return int(amount * 100)


def paise_to_rupees(value):

    return (
        Decimal(int(value)) / Decimal(100)
    ).quantize(
        Decimal("0.01")
    )


# ============================================================
# 2. FINANCIAL YEAR
# ============================================================

def get_financial_year(selected_date):

    payment_date = date.fromisoformat(
        selected_date
    )

    if payment_date.month >= 4:

        start_year = payment_date.year

    else:

        start_year = payment_date.year - 1

    end_year = start_year + 1

    return (
        f"{start_year}-"
        f"{str(end_year)[-2:]}"
    )


# ============================================================
# 3. INITIALIZE PAYMENT TABLES
# ============================================================

def initialize_payment_tables():

    conn = get_connection()

    try:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS payment_sequences (

                financial_year TEXT PRIMARY KEY,

                last_number INTEGER NOT NULL DEFAULT 0

            );


            CREATE TABLE IF NOT EXISTS customer_payments (

                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,

                receipt_number TEXT NOT NULL UNIQUE,

                customer_id INTEGER NOT NULL,

                payment_date TEXT NOT NULL,

                payment_mode TEXT NOT NULL,

                reference_number TEXT,

                total_amount_paise INTEGER NOT NULL,

                received_by INTEGER NOT NULL,

                notes TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (customer_id)
                    REFERENCES customers(customer_id),

                FOREIGN KEY (received_by)
                    REFERENCES users(user_id)

            );


            CREATE TABLE IF NOT EXISTS payment_allocations (

                allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,

                payment_id INTEGER NOT NULL,

                invoice_id INTEGER NOT NULL,

                allocated_amount_paise INTEGER NOT NULL,

                FOREIGN KEY (payment_id)
                    REFERENCES customer_payments(payment_id),

                FOREIGN KEY (invoice_id)
                    REFERENCES invoice_headers(invoice_id)

            );


            CREATE INDEX IF NOT EXISTS idx_customer_payments_customer

            ON customer_payments(customer_id);


            CREATE INDEX IF NOT EXISTS idx_customer_payments_date

            ON customer_payments(payment_date);


            CREATE INDEX IF NOT EXISTS idx_payment_allocations_invoice

            ON payment_allocations(invoice_id);


            CREATE INDEX IF NOT EXISTS idx_payment_allocations_payment

            ON payment_allocations(payment_id);

            """
        )

        # Add a separate payment status column to existing invoices.
        # Do not change invoice_headers.status because dispatch.py
        # uses 'issued' to identify invoices ready for dispatch.

        columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(invoice_headers)"
            ).fetchall()
        }

        if "payment_status" not in columns:

            conn.execute(
                """
                ALTER TABLE invoice_headers

                ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid'
                """
            )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# 4. GENERATE PAYMENT RECEIPT NUMBER
# ============================================================

def generate_receipt_number(conn, payment_date):

    financial_year = get_financial_year(
        payment_date
    )

    sequence = conn.execute(
        """
        SELECT last_number

        FROM payment_sequences

        WHERE financial_year = ?
        """,
        (financial_year,),
    ).fetchone()

    if sequence:

        next_number = (
            int(sequence["last_number"]) + 1
        )

        conn.execute(
            """
            UPDATE payment_sequences

            SET last_number = ?

            WHERE financial_year = ?
            """,
            (
                next_number,
                financial_year,
            ),
        )

    else:

        next_number = 1

        conn.execute(
            """
            INSERT INTO payment_sequences
            (
                financial_year,
                last_number
            )
            VALUES (?, ?)
            """,
            (
                financial_year,
                next_number,
            ),
        )

    return (
        f"PR/{financial_year}/{next_number:04d}"
    )


# ============================================================
# 5. GET INVOICE PAYMENT BALANCE
# ============================================================

def get_invoice_payment_balance(invoice_id):

    conn = get_connection()

    try:

        invoice = conn.execute(
            """
            SELECT
                ih.invoice_id,
                ih.invoice_number,
                ih.customer_id,
                ih.invoice_date,
                ih.grand_total_paise,
                ih.payment_status,
                c.customer_name

            FROM invoice_headers ih

            JOIN customers c
                ON ih.customer_id = c.customer_id

            WHERE ih.invoice_id = ?
            """,
            (invoice_id,),
        ).fetchone()

        if not invoice:

            return None

        allocated = conn.execute(
            """
            SELECT
                COALESCE(
                    SUM(allocated_amount_paise),
                    0
                ) AS total_received

            FROM payment_allocations

            WHERE invoice_id = ?
            """,
            (invoice_id,),
        ).fetchone()

        invoice_total = int(
            invoice["grand_total_paise"]
        )

        received = int(
            allocated["total_received"]
        )

        outstanding = invoice_total - received

        return {

            "invoice_id": invoice["invoice_id"],

            "invoice_number": invoice["invoice_number"],

            "customer_id": invoice["customer_id"],

            "customer_name": invoice["customer_name"],

            "invoice_date": invoice["invoice_date"],

            "invoice_total_paise": invoice_total,

            "received_paise": received,

            "outstanding_paise": outstanding,

            "invoice_total_rupees": paise_to_rupees(
                invoice_total
            ),

            "received_rupees": paise_to_rupees(
                received
            ),

            "outstanding_rupees": paise_to_rupees(
                outstanding
            ),

            "payment_status": (
                "paid"
                if outstanding == 0
                else "partially_paid"
                if received > 0
                else "unpaid"
            ),

        }

    finally:

        conn.close()


# ============================================================
# 6. GET UNPAID AND PARTIALLY PAID INVOICES
# ============================================================

def get_open_invoices(customer_id=None):

    conn = get_connection()

    try:

        query = """
            SELECT

                ih.invoice_id,

                ih.invoice_number,

                ih.customer_id,

                ih.invoice_date,

                ih.grand_total_paise,

                c.customer_name,

                COALESCE(
                    payments.received_paise,
                    0
                ) AS received_paise

            FROM invoice_headers ih

            JOIN customers c
                ON ih.customer_id = c.customer_id

            LEFT JOIN (

                SELECT

                    invoice_id,

                    SUM(allocated_amount_paise) AS received_paise

                FROM payment_allocations

                GROUP BY invoice_id

            ) payments

                ON ih.invoice_id = payments.invoice_id

            WHERE ih.status = 'issued'
        """

        params = []

        if customer_id is not None:

            query += """
                AND ih.customer_id = ?
            """

            params.append(customer_id)

        query += """
            ORDER BY ih.invoice_date ASC, ih.invoice_id ASC
        """

        rows = conn.execute(
            query,
            params,
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            invoice_total = int(
                data["grand_total_paise"]
            )

            received = int(
                data["received_paise"]
            )

            outstanding = (
                invoice_total - received
            )

            if outstanding <= 0:
                continue

            data["outstanding_paise"] = outstanding

            data["invoice_total_rupees"] = paise_to_rupees(
                invoice_total
            )

            data["received_rupees"] = paise_to_rupees(
                received
            )

            data["outstanding_rupees"] = paise_to_rupees(
                outstanding
            )

            data["payment_status"] = (
                "partially_paid"
                if received > 0
                else "unpaid"
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 7. RECORD CUSTOMER PAYMENT
# ============================================================

def record_customer_payment(
    customer_id,
    payment_date,
    payment_mode,
    allocations,
    received_by,
    reference_number="",
    notes="",
):

    """
    Record customer payment against one or more invoices.

    Allocations format:

    [
        (invoice_id, amount_in_rupees),
        ...
    ]

    The payment amount is calculated as the sum of allocations.

    The function:

    1. Verifies customer and user.
    2. Checks invoice ownership.
    3. Checks invoice outstanding balances.
    4. Prevents overpayment.
    5. Generates a payment receipt.
    6. Saves payment and invoice allocations.
    7. Updates invoice payment statuses.
    8. Records an audit entry.

    All operations happen in one transaction.
    """

    # --------------------------------------------------------
    # VALIDATE DATE
    # --------------------------------------------------------

    try:

        selected_date = date.fromisoformat(
            payment_date
        )

    except (TypeError, ValueError):

        raise ValueError(
            "Enter a valid payment date."
        )

    if selected_date > date.today():

        raise ValueError(
            "Payment date cannot be in the future."
        )

    # --------------------------------------------------------
    # VALIDATE PAYMENT MODE
    # --------------------------------------------------------

    valid_modes = [
        "Cash",
        "Bank Transfer",
        "UPI",
        "Cheque",
    ]

    if payment_mode not in valid_modes:

        raise ValueError(
            "Select a valid payment mode."
        )

    if not allocations:

        raise ValueError(
            "Allocate the payment to at least one invoice."
        )

    # --------------------------------------------------------
    # PROCESS ALLOCATION INPUTS
    # --------------------------------------------------------

    processed_allocations = {}

    for invoice_id, amount in allocations:

        try:

            invoice_id = int(invoice_id)

        except (TypeError, ValueError):

            raise ValueError(
                "Invalid invoice selection."
            )

        amount_paise = rupees_to_paise(
            amount
        )

        if invoice_id in processed_allocations:

            processed_allocations[invoice_id] += amount_paise

        else:

            processed_allocations[invoice_id] = amount_paise

    total_amount_paise = sum(
        processed_allocations.values()
    )

    if total_amount_paise <= 0:

        raise ValueError(
            "Payment amount must be greater than zero."
        )

    # --------------------------------------------------------
    # CONNECT AND START TRANSACTION
    # --------------------------------------------------------

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # ----------------------------------------------------
        # VERIFY CUSTOMER
        # ----------------------------------------------------

        customer = conn.execute(
            """
            SELECT customer_id

            FROM customers

            WHERE customer_id = ?
            """,
            (customer_id,),
        ).fetchone()

        if not customer:

            raise ValueError(
                "Customer does not exist."
            )

        # ----------------------------------------------------
        # VERIFY RECEIVING USER
        # ----------------------------------------------------

        user = conn.execute(
            """
            SELECT user_id

            FROM users

            WHERE user_id = ?
            """,
            (received_by,),
        ).fetchone()

        if not user:

            raise ValueError(
                "Receiving user does not exist."
            )

        # ----------------------------------------------------
        # VERIFY INVOICES AND ALLOCATIONS
        # ----------------------------------------------------

        for invoice_id, amount_paise in (
            processed_allocations.items()
        ):

            if amount_paise <= 0:

                raise ValueError(
                    "Invoice allocation must be positive."
                )

            invoice = conn.execute(
                """
                SELECT
                    invoice_id,
                    customer_id,
                    grand_total_paise,
                    status

                FROM invoice_headers

                WHERE invoice_id = ?
                """,
                (invoice_id,),
            ).fetchone()

            if not invoice:

                raise ValueError(
                    f"Invoice ID {invoice_id} does not exist."
                )

            if int(invoice["customer_id"]) != int(customer_id):

                raise ValueError(
                    "The selected invoice does not belong to this customer."
                )

            if invoice["status"] != "issued":

                raise ValueError(
                    "Only issued invoices can receive payments."
                )

            received_row = conn.execute(
                """
                SELECT
                    COALESCE(
                        SUM(allocated_amount_paise),
                        0
                    ) AS received

                FROM payment_allocations

                WHERE invoice_id = ?
                """,
                (invoice_id,),
            ).fetchone()

            already_received = int(
                received_row["received"]
            )

            outstanding = (
                int(invoice["grand_total_paise"])
                - already_received
            )

            if outstanding <= 0:

                raise ValueError(
                    f"Invoice {invoice_id} is already fully paid."
                )

            if amount_paise > outstanding:

                raise ValueError(
                    f"Payment allocation exceeds outstanding "
                    f"balance for invoice {invoice_id}. "
                    f"Outstanding: ₹{paise_to_rupees(outstanding)}."
                )

        # ----------------------------------------------------
        # GENERATE RECEIPT NUMBER
        # ----------------------------------------------------

        receipt_number = generate_receipt_number(
            conn,
            payment_date,
        )

        # ----------------------------------------------------
        # CREATE PAYMENT HEADER
        # ----------------------------------------------------

        cursor = conn.execute(
            """
            INSERT INTO customer_payments
            (
                receipt_number,
                customer_id,
                payment_date,
                payment_mode,
                reference_number,
                total_amount_paise,
                received_by,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt_number,
                customer_id,
                payment_date,
                payment_mode,
                reference_number.strip(),
                total_amount_paise,
                received_by,
                notes,
            ),
        )

        payment_id = cursor.lastrowid

        # ----------------------------------------------------
        # CREATE PAYMENT ALLOCATIONS
        # ----------------------------------------------------

        for invoice_id, amount_paise in (
            processed_allocations.items()
        ):

            conn.execute(
                """
                INSERT INTO payment_allocations
                (
                    payment_id,
                    invoice_id,
                    allocated_amount_paise
                )
                VALUES (?, ?, ?)
                """,
                (
                    payment_id,
                    invoice_id,
                    amount_paise,
                ),
            )

            # Calculate the new outstanding amount.

            received_row = conn.execute(
                """
                SELECT
                    COALESCE(
                        SUM(allocated_amount_paise),
                        0
                    ) AS received

                FROM payment_allocations

                WHERE invoice_id = ?
                """,
                (invoice_id,),
            ).fetchone()

            invoice_total_row = conn.execute(
                """
                SELECT grand_total_paise

                FROM invoice_headers

                WHERE invoice_id = ?
                """,
                (invoice_id,),
            ).fetchone()

            total_received = int(
                received_row["received"]
            )

            invoice_total = int(
                invoice_total_row["grand_total_paise"]
            )

            if total_received >= invoice_total:

                new_status = "paid"

            elif total_received > 0:

                new_status = "partially_paid"

            else:

                new_status = "unpaid"

            # Update separate payment status.
            # Keep invoice_headers.status as 'issued'.

            conn.execute(
                """
                UPDATE invoice_headers

                SET payment_status = ?

                WHERE invoice_id = ?
                """,
                (
                    new_status,
                    invoice_id,
                ),
            )

        # ----------------------------------------------------
        # AUDIT LOG
        # ----------------------------------------------------

        conn.execute(
            """
            INSERT INTO audit_logs
            (
                user_id,
                action,
                entity_type,
                entity_id,
                details
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                received_by,
                "CUSTOMER_PAYMENT_RECORDED",
                "customer_payment",
                payment_id,
                (
                    f"Receipt {receipt_number} recorded. "
                    f"Amount: ₹{paise_to_rupees(total_amount_paise)}. "
                    f"Mode: {payment_mode}."
                ),
            ),
        )

        # ----------------------------------------------------
        # COMMIT
        # ----------------------------------------------------

        conn.commit()

        return {

            "payment_id": payment_id,

            "receipt_number": receipt_number,

            "customer_id": customer_id,

            "total_amount_paise": total_amount_paise,

            "total_amount_rupees": paise_to_rupees(
                total_amount_paise
            ),

            "payment_mode": payment_mode,

            "allocations": len(
                processed_allocations
            ),

        }

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# 8. GET PAYMENT REGISTER
# ============================================================

def get_payment_register(customer_id=None):

    conn = get_connection()

    try:

        query = """
            SELECT
                cp.payment_id,
                cp.receipt_number,
                cp.customer_id,
                c.customer_name,
                cp.payment_date,
                cp.payment_mode,
                cp.reference_number,
                cp.total_amount_paise,
                cp.received_by,
                u.full_name AS received_by_name,
                cp.notes

            FROM customer_payments cp

            JOIN customers c
                ON cp.customer_id = c.customer_id

            JOIN users u
                ON cp.received_by = u.user_id
        """

        params = []

        if customer_id is not None:

            query += """
                WHERE cp.customer_id = ?
            """

            params.append(customer_id)

        query += """
            ORDER BY cp.payment_id DESC
        """

        rows = conn.execute(
            query,
            params,
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["total_amount_rupees"] = paise_to_rupees(
                data["total_amount_paise"]
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 9. GET PAYMENT DETAILS
# ============================================================

def get_payment_details(payment_id):

    conn = get_connection()

    try:

        payment = conn.execute(
            """
            SELECT
                cp.*,
                c.customer_name,
                u.full_name AS received_by_name

            FROM customer_payments cp

            JOIN customers c
                ON cp.customer_id = c.customer_id

            JOIN users u
                ON cp.received_by = u.user_id

            WHERE cp.payment_id = ?
            """,
            (payment_id,),
        ).fetchone()

        if not payment:

            return None

        allocations = conn.execute(
            """
            SELECT
                pa.allocation_id,
                pa.invoice_id,
                ih.invoice_number,
                ih.invoice_date,
                ih.grand_total_paise,
                pa.allocated_amount_paise

            FROM payment_allocations pa

            JOIN invoice_headers ih
                ON pa.invoice_id = ih.invoice_id

            WHERE pa.payment_id = ?

            ORDER BY pa.allocation_id
            """,
            (payment_id,),
        ).fetchall()

        payment_data = dict(payment)

        payment_data["total_amount_rupees"] = paise_to_rupees(
            payment_data["total_amount_paise"]
        )

        allocation_results = []

        for allocation in allocations:

            data = dict(allocation)

            data["allocated_amount_rupees"] = paise_to_rupees(
                data["allocated_amount_paise"]
            )

            data["invoice_total_rupees"] = paise_to_rupees(
                data["grand_total_paise"]
            )

            allocation_results.append(data)

        return {

            "payment": payment_data,

            "allocations": allocation_results,

        }

    finally:

        conn.close()


# ============================================================
# 10. CUSTOMER OUTSTANDING SUMMARY
# ============================================================

def get_customer_outstanding_summary():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                c.customer_id,

                c.customer_name,

                COUNT(ih.invoice_id) AS invoice_count,

                COALESCE(
                    SUM(ih.grand_total_paise),
                    0
                ) AS total_invoiced_paise,

                COALESCE(
                    SUM(
                        COALESCE(p.received_paise, 0)
                    ),
                    0
                ) AS total_received_paise

            FROM customers c

            JOIN invoice_headers ih
                ON c.customer_id = ih.customer_id

            LEFT JOIN (

                SELECT

                    invoice_id,

                    SUM(allocated_amount_paise) AS received_paise

                FROM payment_allocations

                GROUP BY invoice_id

            ) p

                ON ih.invoice_id = p.invoice_id

            WHERE ih.status = 'issued'

            GROUP BY
                c.customer_id,
                c.customer_name

            ORDER BY c.customer_name
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            outstanding = (
                int(data["total_invoiced_paise"])
                - int(data["total_received_paise"])
            )

            data["outstanding_paise"] = outstanding

            data["total_invoiced_rupees"] = paise_to_rupees(
                data["total_invoiced_paise"]
            )

            data["total_received_rupees"] = paise_to_rupees(
                data["total_received_paise"]
            )

            data["outstanding_rupees"] = paise_to_rupees(
                outstanding
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 11. GET OVERDUE INVOICES
# ============================================================

def get_overdue_invoices(
    credit_days=30,
    as_of_date=None,
):

    """
    Returns outstanding invoices whose invoice date is
    older than the configured credit period.

    Default credit period: 30 days.

    This is a project-level overdue rule. Actual credit
    terms can be configured separately for customers.
    """

    if as_of_date is None:

        as_of_date = date.today()

    if isinstance(as_of_date, str):

        as_of_date = date.fromisoformat(
            as_of_date
        )

    if credit_days < 0:

        raise ValueError(
            "Credit days cannot be negative."
        )

    open_invoices = get_open_invoices()

    overdue = []

    for invoice in open_invoices:

        invoice_date = date.fromisoformat(
            invoice["invoice_date"]
        )

        due_date = (
            invoice_date
            + timedelta(days=credit_days)
        )

        if as_of_date > due_date:

            data = dict(invoice)

            data["due_date"] = due_date.isoformat()

            data["overdue_days"] = (
                as_of_date - due_date
            ).days

            overdue.append(data)

    return overdue


# ============================================================
# 12. CUSTOMER PAYMENT HISTORY
# ============================================================

def get_customer_payment_history(customer_id):

    return get_payment_register(
        customer_id=customer_id
    )