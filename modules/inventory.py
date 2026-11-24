import sqlite3

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from database import get_connection


# =====================================================
# QUANTITY AND MONEY CONVERSION
# =====================================================

def quantity_to_milli(quantity, allow_zero=False):

    try:
        value = Decimal(str(quantity))

    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid quantity.")

    if not value.is_finite():
        raise ValueError("Quantity must be finite.")

    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError("Enter a positive quantity.")

    scaled = value * 1000

    if scaled != scaled.to_integral_value():
        raise ValueError(
            "Maximum three decimal places are allowed."
        )

    return int(scaled)


def rupees_to_paise(amount):

    try:
        value = Decimal(str(amount))

    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount.")

    if not value.is_finite() or value < 0:
        raise ValueError("Amount cannot be negative.")

    scaled = value * 100

    if scaled != scaled.to_integral_value():
        raise ValueError(
            "Maximum two decimal places are allowed."
        )

    return int(scaled)


def calculate_line_amount(quantity_milli, rate_paise):

    amount = (
        Decimal(quantity_milli)
        * Decimal(rate_paise)
        / Decimal(1000)
    )

    return int(
        amount.quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP
        )
    )


# =====================================================
# OPENING STOCK
# =====================================================

def get_opening_stock_item_ids():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT DISTINCT inventory_item_id
            FROM stock_movements
            WHERE source_type = 'opening_balance'
            """
        ).fetchall()

        return {
            row["inventory_item_id"]
            for row in rows
        }

    finally:
        conn.close()


def record_opening_stock(entries, user_id):

    """
    Record initial stock for inventory items.

    entries format:
    [
        (item_id, quantity),
        ...
    ]
    """

    if not entries:
        raise ValueError("No opening stock entries provided.")

    processed = []
    seen = set()

    for item_id, quantity in entries:

        if item_id in seen:
            raise ValueError(
                "Duplicate inventory item in opening stock."
            )

        seen.add(item_id)

        quantity_milli = quantity_to_milli(
            quantity,
            allow_zero=True
        )

        if quantity_milli == 0:
            continue

        processed.append(
            (int(item_id), quantity_milli)
        )

    if not processed:
        raise ValueError(
            "Enter at least one positive opening stock quantity."
        )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        for item_id, quantity_milli in processed:

            item = conn.execute(
                """
                SELECT item_id, item_name, active
                FROM inventory_items
                WHERE item_id = ?
                """,
                (item_id,)
            ).fetchone()

            if not item or not item["active"]:
                raise ValueError(
                    f"Invalid or inactive inventory item: {item_id}"
                )

            existing = conn.execute(
                """
                SELECT movement_id
                FROM stock_movements
                WHERE inventory_item_id = ?
                  AND source_type = 'opening_balance'
                LIMIT 1
                """,
                (item_id,)
            ).fetchone()

            if existing:
                raise ValueError(
                    f"Opening stock already exists for {item['item_name']}."
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
                    item_id,
                    quantity_milli,
                    "opening",
                    "opening_balance",
                    item_id,
                    user_id,
                    "Initial opening stock"
                )
            )

        conn.commit()

        return len(processed)

    except Exception:

        conn.rollback()
        raise

    finally:
        conn.close()


# =====================================================
# STOCK SUMMARY
# =====================================================

def get_stock_summary():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                i.item_id,
                i.item_code,
                i.item_name,
                i.category,
                i.base_unit,
                i.reorder_level_milli,

                COALESCE(
                    s.balance_milli,
                    0
                ) AS balance_milli

            FROM inventory_items i

            LEFT JOIN stock_balances s
                ON i.item_id = s.inventory_item_id

            WHERE i.active = 1

            ORDER BY i.category, i.item_name
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["balance"] = (
                data["balance_milli"] / 1000
            )

            data["reorder_level"] = (
                data["reorder_level_milli"] / 1000
            )

            data["stock_status"] = (
                "Low Stock"
                if data["balance_milli"] <= data["reorder_level_milli"]
                else "Available"
            )

            result.append(data)

        return result

    finally:
        conn.close()


# =====================================================
# PURCHASE RECORDING
# =====================================================

def create_purchase(
    supplier_id,
    invoice_reference,
    purchase_date,
    lines,
    user_id
):

    """
    Create a purchase and post its stock receipts.

    lines format:
    [
        (inventory_item_id, quantity, unit_rate_in_rupees),
        ...
    ]
    """

    if not lines:
        raise ValueError("Add at least one purchase item.")

    processed_lines = []

    seen_items = set()

    for item_id, quantity, rate in lines:

        item_id = int(item_id)

        if item_id in seen_items:
            raise ValueError(
                "The same inventory item cannot appear twice."
            )

        seen_items.add(item_id)

        quantity_milli = quantity_to_milli(quantity)

        rate_paise = rupees_to_paise(rate)

        if rate_paise <= 0:
            raise ValueError(
                "Purchase rate must be greater than zero."
            )

        total_paise = calculate_line_amount(
            quantity_milli,
            rate_paise
        )

        processed_lines.append(
            (
                item_id,
                quantity_milli,
                rate_paise,
                total_paise
            )
        )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        supplier = conn.execute(
            """
            SELECT supplier_id
            FROM suppliers
            WHERE supplier_id = ?
            """,
            (supplier_id,)
        ).fetchone()

        if not supplier:
            raise ValueError("Invalid supplier.")

        # Create purchase header.

        cursor = conn.execute(
            """
            INSERT INTO purchases
            (
                supplier_id,
                invoice_reference,
                purchase_date,
                status
            )
            VALUES (?, ?, ?, 'posted')
            """,
            (
                supplier_id,
                invoice_reference.strip(),
                purchase_date
            )
        )

        purchase_id = cursor.lastrowid

        total_purchase_paise = 0

        for (
            item_id,
            quantity_milli,
            rate_paise,
            total_paise
        ) in processed_lines:

            item = conn.execute(
                """
                SELECT item_id, item_name, category
                FROM inventory_items
                WHERE item_id = ? AND active = 1
                """,
                (item_id,)
            ).fetchone()

            if not item:
                raise ValueError(
                    f"Inventory item {item_id} not found."
                )

            if item["category"] not in [
                "raw_material",
                "packaging_material"
            ]:
                raise ValueError(
                    "Purchases can only receive raw materials "
                    "or packaging materials."
                )

            # Save purchase item.

            conn.execute(
                """
                INSERT INTO purchase_items
                (
                    purchase_id,
                    inventory_item_id,
                    quantity_milli,
                    unit_rate_paise,
                    total_amount_paise
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    purchase_id,
                    item_id,
                    quantity_milli,
                    rate_paise,
                    total_paise
                )
            )

            # Update stock through the ledger.

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
                    item_id,
                    quantity_milli,
                    "purchase_receipt",
                    "purchase",
                    purchase_id,
                    user_id,
                    f"Purchase reference: {invoice_reference}"
                )
            )

            total_purchase_paise += total_paise

        conn.commit()

        return {
            "purchase_id": purchase_id,
            "total_paise": total_purchase_paise
        }

    except Exception:

        conn.rollback()
        raise

    finally:
        conn.close()


# =====================================================
# PURCHASE REGISTER
# =====================================================

def get_purchase_register():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                p.purchase_id,
                p.invoice_reference,
                p.purchase_date,
                p.status,
                s.supplier_name,

                COALESCE(
                    SUM(pi.total_amount_paise),
                    0
                ) AS total_amount_paise

            FROM purchases p

            JOIN suppliers s
                ON p.supplier_id = s.supplier_id

            LEFT JOIN purchase_items pi
                ON p.purchase_id = pi.purchase_id

            GROUP BY
                p.purchase_id,
                p.invoice_reference,
                p.purchase_date,
                p.status,
                s.supplier_name

            ORDER BY p.purchase_id DESC
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["total_amount_rupees"] = (
                data["total_amount_paise"] / 100
            )

            result.append(data)

        return result

    finally:
        conn.close()


# =====================================================
# STOCK MOVEMENT LEDGER
# =====================================================

def get_stock_ledger(item_id=None):

    conn = get_connection()

    try:

        if item_id is None:

            rows = conn.execute(
                """
                SELECT
                    m.movement_id,
                    i.item_code,
                    i.item_name,
                    i.base_unit,
                    m.movement_type,
                    m.source_type,
                    m.source_id,
                    m.quantity_delta_milli,
                    m.created_at,
                    u.username,
                    m.notes

                FROM stock_movements m

                JOIN inventory_items i
                    ON m.inventory_item_id = i.item_id

                LEFT JOIN users u
                    ON m.created_by = u.user_id

                ORDER BY m.movement_id DESC
                """
            ).fetchall()

        else:

            rows = conn.execute(
                """
                SELECT
                    m.movement_id,
                    i.item_code,
                    i.item_name,
                    i.base_unit,
                    m.movement_type,
                    m.source_type,
                    m.source_id,
                    m.quantity_delta_milli,
                    m.created_at,
                    u.username,
                    m.notes

                FROM stock_movements m

                JOIN inventory_items i
                    ON m.inventory_item_id = i.item_id

                LEFT JOIN users u
                    ON m.created_by = u.user_id

                WHERE m.inventory_item_id = ?

                ORDER BY m.movement_id DESC
                """,
                (item_id,)
            ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["quantity_change"] = (
                data["quantity_delta_milli"] / 1000
            )

            result.append(data)

        return result

    finally:
        conn.close()