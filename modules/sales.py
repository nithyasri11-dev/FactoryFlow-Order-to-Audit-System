from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)

from database import get_connection


# ============================================================
# 1. INITIALIZE SALES TABLES
# ============================================================

def initialize_sales_tables():

    conn = get_connection()

    try:

        conn.executescript(
            """

            CREATE TABLE IF NOT EXISTS sales_orders (

                order_id INTEGER PRIMARY KEY AUTOINCREMENT,

                customer_id INTEGER NOT NULL,

                order_date TEXT NOT NULL,

                required_date TEXT,

                status TEXT NOT NULL DEFAULT 'pending',

                created_by INTEGER NOT NULL,

                approved_by INTEGER,

                approved_at TEXT,

                rejection_reason TEXT,

                notes TEXT,

                subtotal_paise INTEGER NOT NULL DEFAULT 0,

                total_amount_paise INTEGER NOT NULL DEFAULT 0,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (customer_id)
                    REFERENCES customers(customer_id),

                FOREIGN KEY (created_by)
                    REFERENCES users(user_id),

                FOREIGN KEY (approved_by)
                    REFERENCES users(user_id)

            );


            CREATE TABLE IF NOT EXISTS sales_order_items (

                order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

                order_id INTEGER NOT NULL,

                product_id INTEGER NOT NULL,

                quantity_packets INTEGER NOT NULL,

                unit_rate_paise INTEGER NOT NULL,

                line_total_paise INTEGER NOT NULL,

                FOREIGN KEY (order_id)
                    REFERENCES sales_orders(order_id),

                FOREIGN KEY (product_id)
                    REFERENCES products(product_id)

            );


            CREATE INDEX IF NOT EXISTS idx_sales_orders_status

            ON sales_orders(status);


            CREATE INDEX IF NOT EXISTS idx_sales_orders_customer

            ON sales_orders(customer_id);


            CREATE INDEX IF NOT EXISTS idx_sales_order_items_order

            ON sales_order_items(order_id);

            """
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# 2. MONEY CONVERSION
# ============================================================

def rupees_to_paise(value):

    try:

        amount = Decimal(str(value))

    except (InvalidOperation, ValueError):

        raise ValueError(
            "Enter a valid selling price."
        )

    if not amount.is_finite():

        raise ValueError(
            "Selling price must be finite."
        )

    if amount <= 0:

        raise ValueError(
            "Selling price must be greater than zero."
        )

    amount = amount.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return int(amount * 100)


def paise_to_rupees(value):

    return float(
        Decimal(int(value)) / Decimal(100)
    )


# ============================================================
# 3. CREATE SALES ORDER
# ============================================================

def create_sales_order(
    customer_id,
    order_date,
    required_date,
    order_lines,
    created_by,
    notes="",
):

    """
    order_lines format:

    [
        (product_id, quantity_packets, unit_rate_rupees),
        ...
    ]
    """

    if not order_lines:

        raise ValueError(
            "Add at least one product to the order."
        )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # Verify customer

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
                "Selected customer does not exist."
            )

        # Verify creator

        user = conn.execute(
            """
            SELECT user_id

            FROM users

            WHERE user_id = ?
            """,
            (created_by,),
        ).fetchone()

        if not user:

            raise ValueError(
                "User account does not exist."
            )

        processed_lines = []

        subtotal_paise = 0

        for product_id, quantity, unit_rate in order_lines:

            try:

                product_id = int(product_id)

                quantity = int(quantity)

            except (ValueError, TypeError):

                raise ValueError(
                    "Invalid product or quantity."
                )

            if quantity <= 0:

                raise ValueError(
                    "Product quantity must be positive."
                )

            product = conn.execute(
                """
                SELECT product_id

                FROM products

                WHERE product_id = ?
                """,
                (product_id,),
            ).fetchone()

            if not product:

                raise ValueError(
                    f"Product ID {product_id} does not exist."
                )

            rate_paise = rupees_to_paise(
                unit_rate
            )

            line_total = quantity * rate_paise

            subtotal_paise += line_total

            processed_lines.append(
                (
                    product_id,
                    quantity,
                    rate_paise,
                    line_total,
                )
            )

        # Insert order header

        cursor = conn.execute(
            """
            INSERT INTO sales_orders
            (
                customer_id,
                order_date,
                required_date,
                status,
                created_by,
                notes,
                subtotal_paise,
                total_amount_paise
            )

            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                customer_id,
                order_date,
                required_date,
                created_by,
                notes,
                subtotal_paise,
                subtotal_paise,
            ),
        )

        order_id = cursor.lastrowid

        # Insert order items

        for line in processed_lines:

            conn.execute(
                """
                INSERT INTO sales_order_items
                (
                    order_id,
                    product_id,
                    quantity_packets,
                    unit_rate_paise,
                    line_total_paise
                )

                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    line[0],
                    line[1],
                    line[2],
                    line[3],
                ),
            )

        # Audit record

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
                "SALES_ORDER_CREATED",
                "sales_order",
                order_id,
                (
                    f"Sales order created. "
                    f"Total: ₹{paise_to_rupees(subtotal_paise):.2f}"
                ),
            ),
        )

        conn.commit()

        return {
            "order_id": order_id,
            "subtotal_paise": subtotal_paise,
            "total_amount_paise": subtotal_paise,
            "total_amount_rupees": paise_to_rupees(
                subtotal_paise
            ),
        }

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# 4. GET FINISHED PRODUCT STOCK
# ============================================================

def get_product_stock_availability(product_id):

    """
    Returns:

    - On-hand stock
    - Reserved stock
    - Available stock

    Quantities are returned in packets.
    """

    conn = get_connection()

    try:

        product = conn.execute(
            """
            SELECT
                product_id,
                inventory_item_id

            FROM products

            WHERE product_id = ?
            """,
            (product_id,),
        ).fetchone()

        if not product:

            raise ValueError(
                "Product does not exist."
            )

        inventory_item_id = product["inventory_item_id"]

        if inventory_item_id is None:

            return {
                "on_hand": 0,
                "reserved": 0,
                "available": 0,
            }

        # Read physical stock

        stock_row = conn.execute(
            """
            SELECT
                COALESCE(
                    SUM(quantity_delta_milli),
                    0
                ) AS balance

            FROM stock_movements

            WHERE inventory_item_id = ?
            """,
            (inventory_item_id,),
        ).fetchone()

        on_hand_milli = int(
            stock_row["balance"]
        )

        # Read reserved stock from approved orders

        reserved_row = conn.execute(
            """
            SELECT
                COALESCE(
                    SUM(soi.quantity_packets),
                    0
                ) AS reserved

            FROM sales_order_items soi

            JOIN sales_orders so
                ON soi.order_id = so.order_id

            JOIN products p
                ON soi.product_id = p.product_id

            WHERE p.inventory_item_id = ?

              AND so.status = 'approved'
            """,
            (inventory_item_id,),
        ).fetchone()

        reserved_packets = int(
            reserved_row["reserved"]
        )

        # One finished-goods inventory unit represents one packet.

        on_hand_packets = on_hand_milli // 1000

        available_packets = max(
            0,
            on_hand_packets - reserved_packets,
        )

        return {
            "on_hand": on_hand_packets,
            "reserved": reserved_packets,
            "available": available_packets,
        }

    finally:

        conn.close()


# ============================================================
# 5. GET SALES ORDER REGISTER
# ============================================================

def get_sales_orders(created_by=None):

    conn = get_connection()

    try:

        query = """
            SELECT

                so.order_id,

                so.customer_id,

                c.customer_name,

                so.order_date,

                so.required_date,

                so.status,

                so.created_by,

                u.full_name AS created_by_name,

                so.subtotal_paise,

                so.total_amount_paise,

                so.created_at

            FROM sales_orders so

            JOIN customers c
                ON so.customer_id = c.customer_id

            JOIN users u
                ON so.created_by = u.user_id
        """

        params = []

        if created_by is not None:

            query += """
                WHERE so.created_by = ?
            """

            params.append(created_by)

        query += """
            ORDER BY so.order_id DESC
        """

        rows = conn.execute(
            query,
            params,
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["subtotal_rupees"] = paise_to_rupees(
                data["subtotal_paise"]
            )

            data["total_amount_rupees"] = paise_to_rupees(
                data["total_amount_paise"]
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 6. GET SALES ORDER DETAILS
# ============================================================

def get_sales_order_details(order_id):

    conn = get_connection()

    try:

        order = conn.execute(
            """
            SELECT

                so.*,

                c.customer_name,

                u.full_name AS created_by_name

            FROM sales_orders so

            JOIN customers c
                ON so.customer_id = c.customer_id

            JOIN users u
                ON so.created_by = u.user_id

            WHERE so.order_id = ?
            """,
            (order_id,),
        ).fetchone()

        if not order:

            return None

        # item_code belongs to inventory_items, not products.

        items = conn.execute(
            """
            SELECT

                soi.order_item_id,

                soi.product_id,

                p.product_name,

                p.pack_size_g,

                i.item_code,

                soi.quantity_packets,

                soi.unit_rate_paise,

                soi.line_total_paise

            FROM sales_order_items soi

            JOIN products p
                ON soi.product_id = p.product_id

            JOIN inventory_items i
                ON p.inventory_item_id = i.item_id

            WHERE soi.order_id = ?

            ORDER BY soi.order_item_id
            """,
            (order_id,),
        ).fetchall()

        item_list = []

        for item in items:

            data = dict(item)

            data["unit_rate_rupees"] = paise_to_rupees(
                data["unit_rate_paise"]
            )

            data["line_total_rupees"] = paise_to_rupees(
                data["line_total_paise"]
            )

            item_list.append(data)

        order_data = dict(order)

        order_data["subtotal_rupees"] = paise_to_rupees(
            order_data["subtotal_paise"]
        )

        order_data["total_amount_rupees"] = paise_to_rupees(
            order_data["total_amount_paise"]
        )

        return {
            "order": order_data,
            "items": item_list,
        }

    finally:

        conn.close()


# ============================================================
# 7. APPROVE OR REJECT SALES ORDER
# ============================================================

def review_sales_order(
    order_id,
    reviewer_id,
    decision,
    rejection_reason="",
):

    decision = decision.lower().strip()

    if decision not in ("approve", "reject"):

        raise ValueError(
            "Decision must be approve or reject."
        )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # Verify reviewer

        reviewer = conn.execute(
            """
            SELECT user_id, role

            FROM users

            WHERE user_id = ?
              AND active = 1
            """,
            (reviewer_id,),
        ).fetchone()

        if not reviewer:

            raise ValueError(
                "Reviewer account does not exist or is inactive."
            )

        if reviewer["role"] != "admin":

            raise ValueError(
                "Only administrators can review sales orders."
            )

        # Load order

        order = conn.execute(
            """
            SELECT *

            FROM sales_orders

            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()

        if not order:

            raise ValueError(
                "Sales order not found."
            )

        if order["status"] != "pending":

            raise ValueError(
                "Only pending orders can be reviewed."
            )

        # ----------------------------------------------------
        # REJECT ORDER
        # ----------------------------------------------------

        if decision == "reject":

            if not rejection_reason.strip():

                raise ValueError(
                    "Enter a reason for rejecting the order."
                )

            conn.execute(
                """
                UPDATE sales_orders

                SET

                    status = 'rejected',

                    approved_by = ?,

                    approved_at = CURRENT_TIMESTAMP,

                    rejection_reason = ?

                WHERE order_id = ?
                """,
                (
                    reviewer_id,
                    rejection_reason.strip(),
                    order_id,
                ),
            )

            audit_action = "SALES_ORDER_REJECTED"

            audit_details = (
                f"Order rejected. Reason: {rejection_reason}"
            )

        # ----------------------------------------------------
        # APPROVE ORDER
        # ----------------------------------------------------

        else:

            lines = conn.execute(
                """
                SELECT

                    soi.product_id,

                    soi.quantity_packets,

                    p.inventory_item_id,

                    p.product_name

                FROM sales_order_items soi

                JOIN products p
                    ON soi.product_id = p.product_id

                WHERE soi.order_id = ?
                """,
                (order_id,),
            ).fetchall()

            if not lines:

                raise ValueError(
                    "The sales order has no products."
                )

            requirements = {}

            product_names = {}

            for line in lines:

                inventory_item_id = line["inventory_item_id"]

                if inventory_item_id is None:

                    raise ValueError(
                        f"Finished-goods inventory is not linked "
                        f"to {line['product_name']}."
                    )

                requirements[inventory_item_id] = (
                    requirements.get(inventory_item_id, 0)
                    + int(line["quantity_packets"])
                )

                product_names[inventory_item_id] = (
                    line["product_name"]
                )

            # Verify physical stock and existing reservations

            for inventory_item_id, required_packets in requirements.items():

                stock_row = conn.execute(
                    """
                    SELECT

                        COALESCE(
                            SUM(quantity_delta_milli),
                            0
                        ) AS balance

                    FROM stock_movements

                    WHERE inventory_item_id = ?
                    """,
                    (inventory_item_id,),
                ).fetchone()

                on_hand_packets = (
                    int(stock_row["balance"]) // 1000
                )

                reserved_row = conn.execute(
                    """
                    SELECT

                        COALESCE(
                            SUM(soi.quantity_packets),
                            0
                        ) AS reserved

                    FROM sales_order_items soi

                    JOIN sales_orders so
                        ON soi.order_id = so.order_id

                    JOIN products p
                        ON soi.product_id = p.product_id

                    WHERE p.inventory_item_id = ?

                      AND so.status = 'approved'
                    """,
                    (inventory_item_id,),
                ).fetchone()

                reserved_packets = int(
                    reserved_row["reserved"]
                )

                available_packets = max(
                    0,
                    on_hand_packets - reserved_packets,
                )

                if required_packets > available_packets:

                    raise ValueError(
                        f"Insufficient finished-goods stock for "
                        f"{product_names[inventory_item_id]}. "
                        f"Required: {required_packets}; "
                        f"Available: {available_packets}."
                    )

            # Approve the order

            conn.execute(
                """
                UPDATE sales_orders

                SET

                    status = 'approved',

                    approved_by = ?,

                    approved_at = CURRENT_TIMESTAMP

                WHERE order_id = ?
                """,
                (
                    reviewer_id,
                    order_id,
                ),
            )

            audit_action = "SALES_ORDER_APPROVED"

            audit_details = (
                "Order approved after stock availability verification."
            )

        # ----------------------------------------------------
        # AUDIT RECORD
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
                reviewer_id,
                audit_action,
                "sales_order",
                order_id,
                audit_details,
            ),
        )

        conn.commit()

        return True

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()