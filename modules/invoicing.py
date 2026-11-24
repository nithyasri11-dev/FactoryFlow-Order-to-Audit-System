from datetime import date

from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)

from database import get_connection


# ============================================================
# 1. CONFIGURATION
# ============================================================

# Change this to the state in which the factory is registered.

SUPPLIER_STATE = "Tamil Nadu"


# ============================================================
# 2. INITIALIZE INVOICE TABLES
# ============================================================

def initialize_invoice_tables():

    conn = get_connection()

    try:

        conn.executescript(
            """

            CREATE TABLE IF NOT EXISTS invoice_sequences (

                financial_year TEXT PRIMARY KEY,

                last_number INTEGER NOT NULL DEFAULT 0

            );


            CREATE TABLE IF NOT EXISTS invoice_headers (

                invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,

                invoice_number TEXT NOT NULL UNIQUE,

                order_id INTEGER NOT NULL UNIQUE,

                customer_id INTEGER NOT NULL,

                invoice_date TEXT NOT NULL,

                supplier_state TEXT NOT NULL,

                place_of_supply_state TEXT NOT NULL,

                supply_type TEXT NOT NULL,

                taxable_value_paise INTEGER NOT NULL,

                cgst_paise INTEGER NOT NULL DEFAULT 0,

                sgst_paise INTEGER NOT NULL DEFAULT 0,

                igst_paise INTEGER NOT NULL DEFAULT 0,

                total_tax_paise INTEGER NOT NULL DEFAULT 0,

                grand_total_paise INTEGER NOT NULL,

                status TEXT NOT NULL DEFAULT 'issued',

                created_by INTEGER NOT NULL,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (order_id)
                    REFERENCES sales_orders(order_id),

                FOREIGN KEY (customer_id)
                    REFERENCES customers(customer_id),

                FOREIGN KEY (created_by)
                    REFERENCES users(user_id)

            );


            CREATE TABLE IF NOT EXISTS invoice_items (

                invoice_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

                invoice_id INTEGER NOT NULL,

                product_id INTEGER NOT NULL,

                description TEXT NOT NULL,

                hsn_code TEXT,

                quantity_packets INTEGER NOT NULL,

                unit_rate_paise INTEGER NOT NULL,

                taxable_value_paise INTEGER NOT NULL,

                gst_rate_basis_points INTEGER NOT NULL,

                cgst_paise INTEGER NOT NULL DEFAULT 0,

                sgst_paise INTEGER NOT NULL DEFAULT 0,

                igst_paise INTEGER NOT NULL DEFAULT 0,

                total_tax_paise INTEGER NOT NULL,

                line_total_paise INTEGER NOT NULL,

                FOREIGN KEY (invoice_id)
                    REFERENCES invoice_headers(invoice_id),

                FOREIGN KEY (product_id)
                    REFERENCES products(product_id)

            );


            CREATE INDEX IF NOT EXISTS idx_invoice_date

            ON invoice_headers(invoice_date);


            CREATE INDEX IF NOT EXISTS idx_invoice_customer

            ON invoice_headers(customer_id);


            CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice

            ON invoice_items(invoice_id);

            """
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# 3. FINANCIAL YEAR
# ============================================================

def get_financial_year(invoice_date):

    """
    Indian financial year:

    April to March.

    Examples:

    15 May 2026 -> 2026-27

    15 February 2027 -> 2026-27
    """

    selected_date = date.fromisoformat(
        invoice_date
    )

    if selected_date.month >= 4:

        start_year = selected_date.year

    else:

        start_year = selected_date.year - 1

    end_year = start_year + 1

    return (
        f"{start_year}-"
        f"{str(end_year)[-2:]}"
    )


# ============================================================
# 4. MONEY HELPERS
# ============================================================

def paise_to_rupees(paise):

    return (
        Decimal(int(paise)) / Decimal(100)
    ).quantize(
        Decimal("0.01")
    )


def round_tax_paise(
    amount_paise,
    rate_basis_points,
):

    """
    GST rate examples:

    500 = 5%

    1200 = 12%

    1800 = 18%

    Returns GST amount in paise.
    """

    amount = (
        Decimal(amount_paise)
        * Decimal(rate_basis_points)
        / Decimal(10000)
    )

    return int(
        amount.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def percentage_to_basis_points(value):

    try:

        rate = Decimal(str(value))

    except (InvalidOperation, ValueError):

        raise ValueError(
            "Invalid GST rate."
        )

    if not rate.is_finite():

        raise ValueError(
            "GST rate must be finite."
        )

    if rate < 0 or rate > 100:

        raise ValueError(
            "GST rate must be between 0 and 100."
        )

    return int(
        rate * 100
    )


# ============================================================
# 5. STATE COMPARISON
# ============================================================

def normalize_state(state):

    if not state:

        return ""

    return " ".join(
        str(state).strip().lower().split()
    )


def determine_supply_type(
    supplier_state,
    customer_state,
):

    supplier = normalize_state(
        supplier_state
    )

    customer = normalize_state(
        customer_state
    )

    if not supplier or not customer:

        raise ValueError(
            "Supplier state and customer state are required."
        )

    if supplier == customer:

        return "intra_state"

    return "inter_state"


# ============================================================
# 6. GET APPROVED ORDERS WITHOUT INVOICES
# ============================================================

def get_orders_pending_invoice():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                so.order_id,

                so.customer_id,

                so.order_date,

                so.required_date,

                so.total_amount_paise,

                c.customer_name,

                c.state AS customer_state

            FROM sales_orders so

            JOIN customers c
                ON so.customer_id = c.customer_id

            LEFT JOIN invoice_headers ih
                ON so.order_id = ih.order_id

            WHERE so.status = 'approved'

              AND ih.invoice_id IS NULL

            ORDER BY so.order_id DESC
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["order_total_rupees"] = paise_to_rupees(
                data["total_amount_paise"]
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 7. CREATE GST INVOICE
# ============================================================

def create_invoice_from_order(
    order_id,
    invoice_date,
    created_by,
    supplier_state=SUPPLIER_STATE,
):

    """
    Generate an invoice from an approved sales order.

    The function:

    1. Checks order approval.
    2. Prevents duplicate invoicing.
    3. Generates a financial-year invoice number.
    4. Calculates taxable values.
    5. Calculates CGST and SGST or IGST.
    6. Stores invoice header and invoice lines.
    7. Records an audit log.

    All database changes occur in one transaction.
    """

    # --------------------------------------------------------
    # VALIDATE DATE
    # --------------------------------------------------------

    try:

        selected_date = date.fromisoformat(
            invoice_date
        )

    except (TypeError, ValueError):

        raise ValueError(
            "Enter a valid invoice date in YYYY-MM-DD format."
        )

    if selected_date > date.today():

        raise ValueError(
            "Invoice date cannot be in the future."
        )

    financial_year = get_financial_year(
        invoice_date
    )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # ----------------------------------------------------
        # VERIFY ORDER
        # ----------------------------------------------------

        order = conn.execute(
            """
            SELECT

                so.*,

                c.customer_name,

                c.state AS customer_state

            FROM sales_orders so

            JOIN customers c
                ON so.customer_id = c.customer_id

            WHERE so.order_id = ?
            """,
            (order_id,),
        ).fetchone()

        if not order:

            raise ValueError(
                "Sales order not found."
            )

        if order["status"] != "approved":

            raise ValueError(
                "Only approved sales orders can be invoiced."
            )

        # ----------------------------------------------------
        # CHECK DUPLICATE INVOICE
        # ----------------------------------------------------

        existing_invoice = conn.execute(
            """
            SELECT invoice_number

            FROM invoice_headers

            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()

        if existing_invoice:

            raise ValueError(
                f"This order already has invoice "
                f"{existing_invoice['invoice_number']}."
            )

        # ----------------------------------------------------
        # VERIFY USER
        # ----------------------------------------------------

        user = conn.execute(
            """
            SELECT user_id

            FROM users

            WHERE user_id = ?
              AND active = 1
            """,
            (created_by,),
        ).fetchone()

        if not user:

            raise ValueError(
                "Invoice creator does not exist or is inactive."
            )

        # ----------------------------------------------------
        # DETERMINE GST TYPE
        # ----------------------------------------------------

        customer_state = order["customer_state"]

        supply_type = determine_supply_type(
            supplier_state,
            customer_state,
        )

        # ----------------------------------------------------
        # LOAD ORDER ITEMS
        # ----------------------------------------------------

        order_items = conn.execute(
            """
            SELECT

                soi.product_id,

                soi.quantity_packets,

                soi.unit_rate_paise,

                soi.line_total_paise,

                p.product_name,

                p.hsn_code,

                p.gst_rate_bps

            FROM sales_order_items soi

            JOIN products p
                ON soi.product_id = p.product_id

            WHERE soi.order_id = ?

            ORDER BY soi.order_item_id
            """,
            (order_id,),
        ).fetchall()

        if not order_items:

            raise ValueError(
                "This sales order has no products."
            )

        # ----------------------------------------------------
        # CALCULATE TAX FOR EACH ITEM
        # ----------------------------------------------------

        processed_items = []

        taxable_total = 0

        cgst_total = 0

        sgst_total = 0

        igst_total = 0

        for item in order_items:

            quantity = int(
                item["quantity_packets"]
            )

            unit_rate = int(
                item["unit_rate_paise"]
            )

            taxable_value = (
                quantity * unit_rate
            )

            # gst_rate_bps is already stored in basis points.
            # Do not convert it as though it were a percentage.

            rate_basis_points = int(
                item["gst_rate_bps"]
            )

            if not 0 <= rate_basis_points <= 10000:

                raise ValueError(
                    f"Invalid GST rate for {item['product_name']}."
                )

            total_item_tax = round_tax_paise(
                taxable_value,
                rate_basis_points,
            )

            item_cgst = 0

            item_sgst = 0

            item_igst = 0

            if supply_type == "intra_state":

                item_cgst = total_item_tax // 2

                item_sgst = (
                    total_item_tax - item_cgst
                )

            else:

                item_igst = total_item_tax

            taxable_total += taxable_value

            cgst_total += item_cgst

            sgst_total += item_sgst

            igst_total += item_igst

            processed_items.append({

                "product_id": item["product_id"],

                "description": item["product_name"],

                "hsn_code": item["hsn_code"],

                "quantity": quantity,

                "unit_rate": unit_rate,

                "taxable_value": taxable_value,

                "gst_rate_basis_points": rate_basis_points,

                "cgst": item_cgst,

                "sgst": item_sgst,

                "igst": item_igst,

                "total_tax": total_item_tax,

                "line_total": (
                    taxable_value + total_item_tax
                ),

            })

        # ----------------------------------------------------
        # CALCULATE GRAND TOTAL
        # ----------------------------------------------------

        total_tax = (
            cgst_total
            + sgst_total
            + igst_total
        )

        grand_total = (
            taxable_total + total_tax
        )

        # ----------------------------------------------------
        # GENERATE INVOICE NUMBER
        # ----------------------------------------------------

        sequence = conn.execute(
            """
            SELECT last_number

            FROM invoice_sequences

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
                UPDATE invoice_sequences

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
                INSERT INTO invoice_sequences
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

        invoice_number = (
            f"FF/{financial_year}/{next_number:04d}"
        )

        # ----------------------------------------------------
        # INSERT INVOICE HEADER
        # ----------------------------------------------------

        cursor = conn.execute(
            """
            INSERT INTO invoice_headers
            (
                invoice_number,
                order_id,
                customer_id,
                invoice_date,
                supplier_state,
                place_of_supply_state,
                supply_type,
                taxable_value_paise,
                cgst_paise,
                sgst_paise,
                igst_paise,
                total_tax_paise,
                grand_total_paise,
                status,
                created_by
            )

            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_number,
                order_id,
                order["customer_id"],
                invoice_date,
                supplier_state,
                customer_state,
                supply_type,
                taxable_total,
                cgst_total,
                sgst_total,
                igst_total,
                total_tax,
                grand_total,
                "issued",
                created_by,
            ),
        )

        invoice_id = cursor.lastrowid

        # ----------------------------------------------------
        # INSERT INVOICE ITEMS
        # ----------------------------------------------------

        for item in processed_items:

            conn.execute(
                """
                INSERT INTO invoice_items
                (
                    invoice_id,
                    product_id,
                    description,
                    hsn_code,
                    quantity_packets,
                    unit_rate_paise,
                    taxable_value_paise,
                    gst_rate_basis_points,
                    cgst_paise,
                    sgst_paise,
                    igst_paise,
                    total_tax_paise,
                    line_total_paise
                )

                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    item["product_id"],
                    item["description"],
                    item["hsn_code"],
                    item["quantity"],
                    item["unit_rate"],
                    item["taxable_value"],
                    item["gst_rate_basis_points"],
                    item["cgst"],
                    item["sgst"],
                    item["igst"],
                    item["total_tax"],
                    item["line_total"],
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
                created_by,
                "GST_INVOICE_CREATED",
                "invoice",
                invoice_id,
                (
                    f"Invoice {invoice_number} created "
                    f"for sales order {order_id}. "
                    f"Grand total: ₹{paise_to_rupees(grand_total)}"
                ),
            ),
        )

        # ----------------------------------------------------
        # COMMIT TRANSACTION
        # ----------------------------------------------------

        conn.commit()

        return {

            "invoice_id": invoice_id,

            "invoice_number": invoice_number,

            "order_id": order_id,

            "taxable_value_paise": taxable_total,

            "cgst_paise": cgst_total,

            "sgst_paise": sgst_total,

            "igst_paise": igst_total,

            "total_tax_paise": total_tax,

            "grand_total_paise": grand_total,

            "grand_total_rupees": paise_to_rupees(
                grand_total
            ),

            "supply_type": supply_type,

        }

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# 8. GET INVOICE REGISTER
# ============================================================

def get_invoice_register():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                ih.invoice_id,

                ih.invoice_number,

                ih.order_id,

                ih.customer_id,

                c.customer_name,

                ih.invoice_date,

                ih.supply_type,

                ih.taxable_value_paise,

                ih.total_tax_paise,

                ih.grand_total_paise,

                ih.status

            FROM invoice_headers ih

            JOIN customers c
                ON ih.customer_id = c.customer_id

            ORDER BY ih.invoice_id DESC
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["taxable_value_rupees"] = paise_to_rupees(
                data["taxable_value_paise"]
            )

            data["total_tax_rupees"] = paise_to_rupees(
                data["total_tax_paise"]
            )

            data["grand_total_rupees"] = paise_to_rupees(
                data["grand_total_paise"]
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 9. GET INVOICE DETAILS
# ============================================================

def get_invoice_details(invoice_id):

    conn = get_connection()

    try:

        invoice = conn.execute(
            """
            SELECT

                ih.*,

                c.customer_name,

                c.state AS customer_state,

                c.gstin AS customer_gstin

            FROM invoice_headers ih

            JOIN customers c
                ON ih.customer_id = c.customer_id

            WHERE ih.invoice_id = ?
            """,
            (invoice_id,),
        ).fetchone()

        if not invoice:

            return None

        items = conn.execute(
            """
            SELECT

                ii.*,

                p.pack_size_g

            FROM invoice_items ii

            JOIN products p
                ON ii.product_id = p.product_id

            WHERE ii.invoice_id = ?

            ORDER BY ii.invoice_item_id
            """,
            (invoice_id,),
        ).fetchall()

        invoice_data = dict(invoice)

        monetary_fields = [
            "taxable_value_paise",
            "cgst_paise",
            "sgst_paise",
            "igst_paise",
            "total_tax_paise",
            "grand_total_paise",
        ]

        for field in monetary_fields:

            invoice_data[
                field.replace("_paise", "_rupees")
            ] = paise_to_rupees(
                invoice_data[field]
            )

        item_results = []

        for item in items:

            data = dict(item)

            data["unit_rate_rupees"] = paise_to_rupees(
                data["unit_rate_paise"]
            )

            data["taxable_value_rupees"] = paise_to_rupees(
                data["taxable_value_paise"]
            )

            data["cgst_rupees"] = paise_to_rupees(
                data["cgst_paise"]
            )

            data["sgst_rupees"] = paise_to_rupees(
                data["sgst_paise"]
            )

            data["igst_rupees"] = paise_to_rupees(
                data["igst_paise"]
            )

            data["total_tax_rupees"] = paise_to_rupees(
                data["total_tax_paise"]
            )

            data["line_total_rupees"] = paise_to_rupees(
                data["line_total_paise"]
            )

            data["gst_rate_percent"] = (
                data["gst_rate_basis_points"] / 100
            )

            item_results.append(data)

        return {

            "invoice": invoice_data,

            "items": item_results,

        }

    finally:

        conn.close()