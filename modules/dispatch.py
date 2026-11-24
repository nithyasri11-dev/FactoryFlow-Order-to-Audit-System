from datetime import date
from database import get_connection


# ============================================================
# 1. INITIALIZE DISPATCH TABLES
# ============================================================

def initialize_dispatch_tables():

    conn = get_connection()

    try:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dispatch_sequences (

                financial_year TEXT PRIMARY KEY,

                last_number INTEGER NOT NULL DEFAULT 0

            );


            CREATE TABLE IF NOT EXISTS dispatch_headers (

                dispatch_id INTEGER PRIMARY KEY AUTOINCREMENT,

                challan_number TEXT NOT NULL UNIQUE,

                order_id INTEGER NOT NULL,

                invoice_id INTEGER NOT NULL,

                dispatch_date TEXT NOT NULL,

                vehicle_number TEXT,

                transporter_name TEXT,

                driver_name TEXT,

                driver_phone TEXT,

                tracking_reference TEXT,

                status TEXT NOT NULL DEFAULT 'dispatched',

                created_by INTEGER NOT NULL,

                delivered_date TEXT,

                received_by TEXT,

                delivery_notes TEXT,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                updated_at TEXT,

                FOREIGN KEY (order_id)
                    REFERENCES sales_orders(order_id),

                FOREIGN KEY (invoice_id)
                    REFERENCES invoice_headers(invoice_id),

                FOREIGN KEY (created_by)
                    REFERENCES users(user_id)

            );


            CREATE TABLE IF NOT EXISTS dispatch_items (

                dispatch_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

                dispatch_id INTEGER NOT NULL,

                product_id INTEGER NOT NULL,

                quantity_packets INTEGER NOT NULL,

                FOREIGN KEY (dispatch_id)
                    REFERENCES dispatch_headers(dispatch_id),

                FOREIGN KEY (product_id)
                    REFERENCES products(product_id)

            );


            CREATE INDEX IF NOT EXISTS idx_dispatch_order
            ON dispatch_headers(order_id);


            CREATE INDEX IF NOT EXISTS idx_dispatch_status
            ON dispatch_headers(status);


            CREATE INDEX IF NOT EXISTS idx_dispatch_items
            ON dispatch_items(dispatch_id);


            """
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# 2. FINANCIAL YEAR
# ============================================================

def get_financial_year(selected_date):

    dispatch_date = date.fromisoformat(
        selected_date
    )

    if dispatch_date.month >= 4:

        start_year = dispatch_date.year

    else:

        start_year = dispatch_date.year - 1

    end_year = start_year + 1

    return (
        f"{start_year}-"
        f"{str(end_year)[-2:]}"
    )


# ============================================================
# 3. GENERATE DELIVERY CHALLAN NUMBER
# ============================================================

def generate_challan_number(conn, dispatch_date):

    financial_year = get_financial_year(
        dispatch_date
    )

    sequence = conn.execute(
        """
        SELECT last_number

        FROM dispatch_sequences

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
            UPDATE dispatch_sequences

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
            INSERT INTO dispatch_sequences
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
        f"DC/{financial_year}/{next_number:04d}"
    )


# ============================================================
# 4. GET ORDERS READY FOR DISPATCH
# ============================================================

def get_orders_ready_for_dispatch():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                so.order_id,
                so.customer_id,
                so.order_date,
                so.required_date,
                so.status,

                c.customer_name,
                c.state AS customer_state,

                ih.invoice_id,
                ih.invoice_number,
                ih.invoice_date,
                ih.grand_total_paise

            FROM sales_orders so

            JOIN customers c
                ON so.customer_id = c.customer_id

            JOIN invoice_headers ih
                ON so.order_id = ih.order_id

            WHERE so.status = 'approved'
              AND ih.status = 'issued'

            ORDER BY so.order_id DESC
            """
        ).fetchall()

        result = []

        for row in rows:

            order = dict(row)

            details = get_order_dispatch_details(
                order["order_id"]
            )

            if not details:
                continue

            remaining = sum(
                item["remaining_quantity"]
                for item in details["items"]
            )

            if remaining > 0:

                order["remaining_packets"] = remaining

                result.append(order)

        return result

    finally:

        conn.close()


# ============================================================
# 5. GET ORDER DISPATCH DETAILS
# ============================================================

def get_order_dispatch_details(order_id):

    conn = get_connection()

    try:

        order = conn.execute(
            """
            SELECT
                so.order_id,
                so.customer_id,
                so.order_date,
                so.required_date,
                so.status,

                c.customer_name,
                c.state AS customer_state,

                ih.invoice_id,
                ih.invoice_number,
                ih.invoice_date,
                ih.grand_total_paise

            FROM sales_orders so

            JOIN customers c
                ON so.customer_id = c.customer_id

            LEFT JOIN invoice_headers ih
                ON so.order_id = ih.order_id

            WHERE so.order_id = ?
            """,
            (order_id,),
        ).fetchone()

        if not order:

            return None

        items = conn.execute(
            """
            SELECT

                soi.product_id,

                p.product_name,

                p.pack_size_g,

                p.inventory_item_id,

                SUM(soi.quantity_packets) AS ordered_quantity,

                COALESCE(

                    (
                        SELECT SUM(di.quantity_packets)

                        FROM dispatch_items di

                        JOIN dispatch_headers dh
                            ON di.dispatch_id = dh.dispatch_id

                        WHERE dh.order_id = ?
                          AND di.product_id = soi.product_id

                    ),

                    0

                ) AS dispatched_quantity

            FROM sales_order_items soi

            JOIN products p
                ON soi.product_id = p.product_id

            WHERE soi.order_id = ?

            GROUP BY
                soi.product_id,
                p.product_name,
                p.pack_size_g,
                p.inventory_item_id

            ORDER BY soi.product_id
            """,
            (
                order_id,
                order_id,
            ),
        ).fetchall()

        item_results = []

        for item in items:

            data = dict(item)

            data["remaining_quantity"] = (
                int(data["ordered_quantity"])
                - int(data["dispatched_quantity"])
            )

            item_results.append(data)

        return {

            "order": dict(order),

            "items": item_results,

        }

    finally:

        conn.close()


# ============================================================
# 6. CREATE DISPATCH
# ============================================================

def create_dispatch(
    order_id,
    dispatch_date,
    dispatch_lines,
    vehicle_number,
    transporter_name,
    driver_name,
    driver_phone,
    tracking_reference,
    created_by,
    notes="",
):

    """
    dispatch_lines format:

    [
        (product_id, quantity_packets),
        ...
    ]

    Features:

    1. Verify approved sales order.
    2. Verify invoice exists.
    3. Check remaining order quantity.
    4. Protect stock reserved for other approved orders.
    5. Deduct dispatched finished goods.
    6. Generate delivery challan.
    7. Record dispatch items.
    8. Update completed order status.
    9. Record audit log.

    Everything is handled in one transaction.
    """

    # --------------------------------------------------------
    # VALIDATE INPUT
    # --------------------------------------------------------

    try:

        selected_date = date.fromisoformat(
            dispatch_date
        )

    except (TypeError, ValueError):

        raise ValueError(
            "Enter a valid dispatch date."
        )

    if selected_date > date.today():

        raise ValueError(
            "Dispatch date cannot be in the future."
        )

    if not dispatch_lines:

        raise ValueError(
            "Add at least one product to the dispatch."
        )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # ----------------------------------------------------
        # VERIFY ORDER
        # ----------------------------------------------------

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
                "Sales order does not exist."
            )

        if order["status"] != "approved":

            raise ValueError(
                "Only approved sales orders can be dispatched."
            )

        # ----------------------------------------------------
        # VERIFY INVOICE
        # ----------------------------------------------------

        invoice = conn.execute(
            """
            SELECT invoice_id

            FROM invoice_headers

            WHERE order_id = ?

              AND status = 'issued'
            """,
            (order_id,),
        ).fetchone()

        if not invoice:

            raise ValueError(
                "Generate a valid GST invoice before dispatching this order."
            )

        invoice_id = invoice["invoice_id"]

        # ----------------------------------------------------
        # VERIFY USER
        # ----------------------------------------------------

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
                "Dispatch creator does not exist."
            )

        # ----------------------------------------------------
        # GET ORDER PROGRESS
        # ----------------------------------------------------

        order_items = conn.execute(
            """
            SELECT

                soi.product_id,

                SUM(soi.quantity_packets) AS ordered_quantity,

                COALESCE(

                    (
                        SELECT SUM(di.quantity_packets)

                        FROM dispatch_items di

                        JOIN dispatch_headers dh
                            ON di.dispatch_id = dh.dispatch_id

                        WHERE dh.order_id = ?
                          AND di.product_id = soi.product_id

                    ),

                    0

                ) AS dispatched_quantity

            FROM sales_order_items soi

            WHERE soi.order_id = ?

            GROUP BY soi.product_id
            """,
            (
                order_id,
                order_id,
            ),
        ).fetchall()

        order_progress = {}

        for item in order_items:

            ordered = int(
                item["ordered_quantity"]
            )

            dispatched = int(
                item["dispatched_quantity"]
            )

            order_progress[
                int(item["product_id"])
            ] = {

                "ordered": ordered,

                "dispatched": dispatched,

                "remaining": ordered - dispatched,

            }

        # ----------------------------------------------------
        # VALIDATE DISPATCH LINES
        # ----------------------------------------------------

        requested_by_product = {}

        for product_id, quantity in dispatch_lines:

            try:

                product_id = int(product_id)

                quantity = int(quantity)

            except (ValueError, TypeError):

                raise ValueError(
                    "Invalid product or dispatch quantity."
                )

            if quantity <= 0:

                raise ValueError(
                    "Dispatch quantities must be positive integers."
                )

            if product_id not in order_progress:

                raise ValueError(
                    "The selected product does not belong to this order."
                )

            requested_by_product[product_id] = (
                requested_by_product.get(product_id, 0)
                + quantity
            )

        if not requested_by_product:

            raise ValueError(
                "No valid products were selected."
            )

        for product_id, quantity in requested_by_product.items():

            remaining = order_progress[
                product_id
            ]["remaining"]

            if quantity > remaining:

                raise ValueError(
                    f"Dispatch quantity exceeds remaining "
                    f"order quantity for product ID {product_id}. "
                    f"Remaining: {remaining}; Requested: {quantity}."
                )

        # ----------------------------------------------------
        # LOAD PRODUCT INVENTORY LINKS
        # ----------------------------------------------------

        product_ids = list(
            requested_by_product.keys()
        )

        placeholders = ",".join(
            "?" for _ in product_ids
        )

        products = conn.execute(
            f"""
            SELECT
                product_id,
                product_name,
                inventory_item_id

            FROM products

            WHERE product_id IN ({placeholders})
            """,
            product_ids,
        ).fetchall()

        product_data = {
            int(product["product_id"]): dict(product)
            for product in products
        }

        # ----------------------------------------------------
        # AGGREGATE REQUESTED QUANTITIES
        # BY INVENTORY ITEM
        # ----------------------------------------------------

        requested_by_inventory = {}

        for product_id, quantity in requested_by_product.items():

            product = product_data[product_id]

            inventory_item_id = product["inventory_item_id"]

            if inventory_item_id is None:

                raise ValueError(
                    f"Finished-goods inventory is not linked "
                    f"to {product['product_name']}."
                )

            inventory_item_id = int(
                inventory_item_id
            )

            requested_by_inventory[inventory_item_id] = (
                requested_by_inventory.get(
                    inventory_item_id,
                    0,
                )
                + quantity
            )

        # ----------------------------------------------------
        # CHECK STOCK WHILE PRESERVING OTHER RESERVATIONS
        # ----------------------------------------------------

        for inventory_item_id, requested_quantity in (
            requested_by_inventory.items()
        ):

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

            # Find outstanding approved quantities
            # belonging to other orders.

            reserved_row = conn.execute(
                """
                SELECT
                    COALESCE(
                        SUM(
                            soi.quantity_packets
                            - COALESCE(d.dispatched_quantity, 0)
                        ),
                        0
                    ) AS reserved_quantity

                FROM sales_orders so

                JOIN sales_order_items soi
                    ON so.order_id = soi.order_id

                JOIN products p
                    ON soi.product_id = p.product_id

                LEFT JOIN (

                    SELECT
                        dh.order_id,
                        di.product_id,
                        SUM(di.quantity_packets) AS dispatched_quantity

                    FROM dispatch_headers dh

                    JOIN dispatch_items di
                        ON dh.dispatch_id = di.dispatch_id

                    GROUP BY
                        dh.order_id,
                        di.product_id

                ) d

                    ON d.order_id = so.order_id
                   AND d.product_id = soi.product_id

                WHERE so.status = 'approved'
                  AND so.order_id != ?
                  AND p.inventory_item_id = ?
                """,
                (
                    order_id,
                    inventory_item_id,
                ),
            ).fetchone()

            reserved_by_others = int(
                reserved_row["reserved_quantity"]
            )

            if (
                on_hand_packets
                < requested_quantity + reserved_by_others
            ):

                raise ValueError(
                    "Insufficient finished-goods stock. "
                    f"On-hand: {on_hand_packets}; "
                    f"Requested for this dispatch: {requested_quantity}; "
                    f"Reserved for other orders: {reserved_by_others}."
                )

        # ----------------------------------------------------
        # GENERATE DELIVERY CHALLAN
        # ----------------------------------------------------

        challan_number = generate_challan_number(
            conn,
            dispatch_date,
        )

        # ----------------------------------------------------
        # CREATE DISPATCH HEADER
        # ----------------------------------------------------

        cursor = conn.execute(
            """
            INSERT INTO dispatch_headers
            (
                challan_number,
                order_id,
                invoice_id,
                dispatch_date,
                vehicle_number,
                transporter_name,
                driver_name,
                driver_phone,
                tracking_reference,
                status,
                created_by,
                delivery_notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challan_number,
                order_id,
                invoice_id,
                dispatch_date,
                vehicle_number.strip(),
                transporter_name.strip(),
                driver_name.strip(),
                driver_phone.strip(),
                tracking_reference.strip(),
                "dispatched",
                created_by,
                notes,
            ),
        )

        dispatch_id = cursor.lastrowid

        # ----------------------------------------------------
        # INSERT DISPATCH ITEMS AND DEDUCT STOCK
        # ----------------------------------------------------

        for product_id, quantity in requested_by_product.items():

            product = product_data[product_id]

            inventory_item_id = int(
                product["inventory_item_id"]
            )

            conn.execute(
                """
                INSERT INTO dispatch_items
                (
                    dispatch_id,
                    product_id,
                    quantity_packets
                )
                VALUES (?, ?, ?)
                """,
                (
                    dispatch_id,
                    product_id,
                    quantity,
                ),
            )

            conn.execute(
                """
                INSERT INTO stock_movements
                (
                    inventory_item_id,
                    quantity_delta_milli,
                    movement_type,
                    source_type,
                    source_id,
                    created_by,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inventory_item_id,
                    -quantity * 1000,
                    "dispatch",
                    "dispatch",
                    dispatch_id,
                    created_by,
                    f"Goods dispatched under {challan_number}",
                ),
            )

        # ----------------------------------------------------
        # CHECK WHETHER THE WHOLE ORDER IS DISPATCHED
        # ----------------------------------------------------

        remaining_row = conn.execute(
            """
            SELECT

                SUM(
                    soi.quantity_packets
                    - COALESCE(d.dispatched_quantity, 0)
                ) AS remaining_quantity

            FROM sales_order_items soi

            LEFT JOIN (

                SELECT
                    dh.order_id,
                    di.product_id,
                    SUM(di.quantity_packets) AS dispatched_quantity

                FROM dispatch_headers dh

                JOIN dispatch_items di
                    ON dh.dispatch_id = di.dispatch_id

                GROUP BY
                    dh.order_id,
                    di.product_id

            ) d

                ON d.order_id = soi.order_id
               AND d.product_id = soi.product_id

            WHERE soi.order_id = ?
            """,
            (order_id,),
        ).fetchone()

        remaining_quantity = int(
            remaining_row["remaining_quantity"] or 0
        )

        if remaining_quantity == 0:

            conn.execute(
                """
                UPDATE sales_orders

                SET status = 'dispatched'

                WHERE order_id = ?
                """,
                (order_id,),
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
                "DISPATCH_CREATED",
                "dispatch",
                dispatch_id,
                (
                    f"Dispatch {challan_number} created "
                    f"for sales order {order_id}. "
                    f"Remaining quantity: {remaining_quantity} packets."
                ),
            ),
        )

        conn.commit()

        return {

            "dispatch_id": dispatch_id,

            "challan_number": challan_number,

            "order_id": order_id,

            "invoice_id": invoice_id,

            "remaining_quantity": remaining_quantity,

            "status": "dispatched",

        }

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# 7. GET DISPATCH REGISTER
# ============================================================

def get_dispatch_register():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                dh.dispatch_id,
                dh.challan_number,
                dh.order_id,
                dh.invoice_id,
                dh.dispatch_date,
                dh.vehicle_number,
                dh.transporter_name,
                dh.driver_name,
                dh.driver_phone,
                dh.tracking_reference,
                dh.status,
                dh.delivered_date,
                dh.received_by,
                c.customer_name,
                ih.invoice_number,
                u.full_name AS created_by_name

            FROM dispatch_headers dh

            JOIN sales_orders so
                ON dh.order_id = so.order_id

            JOIN customers c
                ON so.customer_id = c.customer_id

            JOIN invoice_headers ih
                ON dh.invoice_id = ih.invoice_id

            JOIN users u
                ON dh.created_by = u.user_id

            ORDER BY dh.dispatch_id DESC
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            items = conn.execute(
                """
                SELECT
                    COALESCE(
                        SUM(quantity_packets),
                        0
                    ) AS total_packets

                FROM dispatch_items

                WHERE dispatch_id = ?
                """,
                (data["dispatch_id"],),
            ).fetchone()

            data["total_packets"] = int(
                items["total_packets"]
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 8. GET DISPATCH DETAILS
# ============================================================

def get_dispatch_details(dispatch_id):

    conn = get_connection()

    try:

        dispatch = conn.execute(
            """
            SELECT
                dh.*,
                so.order_id,
                c.customer_name,
                c.state AS customer_state,
                ih.invoice_number,
                ih.invoice_date

            FROM dispatch_headers dh

            JOIN sales_orders so
                ON dh.order_id = so.order_id

            JOIN customers c
                ON so.customer_id = c.customer_id

            JOIN invoice_headers ih
                ON dh.invoice_id = ih.invoice_id

            WHERE dh.dispatch_id = ?
            """,
            (dispatch_id,),
        ).fetchone()

        if not dispatch:

            return None

        items = conn.execute(
            """
            SELECT
                di.product_id,
                p.product_name,
                p.pack_size_g,
                di.quantity_packets

            FROM dispatch_items di

            JOIN products p
                ON di.product_id = p.product_id

            WHERE di.dispatch_id = ?

            ORDER BY di.dispatch_item_id
            """,
            (dispatch_id,),
        ).fetchall()

        return {

            "dispatch": dict(dispatch),

            "items": [
                dict(item)
                for item in items
            ],

        }

    finally:

        conn.close()


# ============================================================
# 9. MARK DISPATCH AS DELIVERED
# ============================================================

def mark_dispatch_delivered(
    dispatch_id,
    delivered_date,
    received_by,
    delivery_notes,
    updated_by,
):

    try:

        selected_date = date.fromisoformat(
            delivered_date
        )

    except (TypeError, ValueError):

        raise ValueError(
            "Enter a valid delivery date."
        )

    if selected_date > date.today():

        raise ValueError(
            "Delivery date cannot be in the future."
        )

    if not received_by.strip():

        raise ValueError(
            "Enter the name of the person receiving the goods."
        )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        dispatch = conn.execute(
            """
            SELECT *
            FROM dispatch_headers
            WHERE dispatch_id = ?
            """,
            (dispatch_id,),
        ).fetchone()

        if not dispatch:

            raise ValueError(
                "Dispatch record not found."
            )

        if dispatch["status"] == "delivered":

            raise ValueError(
                "This dispatch has already been marked as delivered."
            )

        if dispatch["status"] != "dispatched":

            raise ValueError(
                "Only dispatched records can be marked as delivered."
            )

        conn.execute(
            """
            UPDATE dispatch_headers

            SET
                status = 'delivered',
                delivered_date = ?,
                received_by = ?,
                delivery_notes = ?,
                updated_at = CURRENT_TIMESTAMP

            WHERE dispatch_id = ?
            """,
            (
                delivered_date,
                received_by.strip(),
                delivery_notes,
                dispatch_id,
            ),
        )

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
                updated_by,
                "DELIVERY_CONFIRMED",
                "dispatch",
                dispatch_id,
                (
                    f"Dispatch {dispatch['challan_number']} "
                    f"delivered to {received_by.strip()} "
                    f"on {delivered_date}."
                ),
            ),
        )

        conn.commit()

        return True

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()