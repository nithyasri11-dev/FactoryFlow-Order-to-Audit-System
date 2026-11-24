import sqlite3
from decimal import Decimal, InvalidOperation

from database import get_connection


def convert_to_milli(quantity):
    """Convert a quantity into thousandths."""

    try:
        value = Decimal(str(quantity))
    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid quantity.")

    if not value.is_finite() or value <= 0:
        raise ValueError("Quantity must be greater than zero.")

    scaled = value * 1000

    if scaled != scaled.to_integral_value():
        raise ValueError(
            "Only three decimal places are supported."
        )

    return int(scaled)


def create_bom(product_id, expected_yield, components):
    """
    Create a new Bill of Materials.

    components format:
    [
        (inventory_item_id, quantity_per_batch),
        ...
    ]
    """

    if int(expected_yield) <= 0:
        raise ValueError("Expected yield must be positive.")

    if not components:
        raise ValueError("At least one material is required.")

    conn = get_connection()

    try:
        conn.execute("BEGIN IMMEDIATE")

        product = conn.execute(
            """
            SELECT product_id
            FROM products
            WHERE product_id = ?
            """,
            (product_id,)
        ).fetchone()

        if not product:
            raise ValueError("Selected product does not exist.")

        processed_items = []

        seen_items = set()

        for item_id, quantity in components:

            if item_id in seen_items:
                raise ValueError(
                    "The same inventory item cannot be added twice."
                )

            seen_items.add(item_id)

            item = conn.execute(
                """
                SELECT item_id, category, item_name
                FROM inventory_items
                WHERE item_id = ? AND active = 1
                """,
                (item_id,)
            ).fetchone()

            if not item:
                raise ValueError(
                    f"Inventory item {item_id} does not exist."
                )

            if item["category"] not in [
                "raw_material",
                "packaging_material"
            ]:
                raise ValueError(
                    f"{item['item_name']} is not a valid BOM component."
                )

            quantity_milli = convert_to_milli(quantity)

            processed_items.append(
                (item_id, quantity_milli)
            )

        # Find the next BOM version.
        result = conn.execute(
            """
            SELECT COALESCE(MAX(version), 0) + 1
            FROM boms
            WHERE product_id = ?
            """,
            (product_id,)
        ).fetchone()

        version = result[0]

        # Deactivate previous BOM versions.
        conn.execute(
            """
            UPDATE boms
            SET active = 0
            WHERE product_id = ?
            """,
            (product_id,)
        )

        # Create the new BOM.
        cursor = conn.execute(
            """
            INSERT INTO boms
            (
                product_id,
                version,
                expected_yield_packets,
                active
            )
            VALUES (?, ?, ?, 1)
            """,
            (
                product_id,
                version,
                int(expected_yield)
            )
        )

        bom_id = cursor.lastrowid

        # Insert BOM components.
        for item_id, quantity_milli in processed_items:

            conn.execute(
                """
                INSERT INTO bom_items
                (
                    bom_id,
                    inventory_item_id,
                    quantity_per_batch_milli
                )
                VALUES (?, ?, ?)
                """,
                (
                    bom_id,
                    item_id,
                    quantity_milli
                )
            )

        conn.commit()

        return bom_id

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def get_boms():

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                b.bom_id,
                b.version,
                b.expected_yield_packets,
                b.active,
                p.product_name,
                p.pack_size_g
            FROM boms b
            JOIN products p
                ON b.product_id = p.product_id
            ORDER BY p.product_name, b.version DESC
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def get_bom_details(bom_id):

    conn = get_connection()

    try:

        bom = conn.execute(
            """
            SELECT
                b.bom_id,
                b.version,
                b.expected_yield_packets,
                b.active,
                p.product_name
            FROM boms b
            JOIN products p
                ON b.product_id = p.product_id
            WHERE b.bom_id = ?
            """,
            (bom_id,)
        ).fetchone()

        if not bom:
            return None

        components = conn.execute(
            """
            SELECT
                i.item_code,
                i.item_name,
                i.base_unit,
                bi.quantity_per_batch_milli
            FROM bom_items bi
            JOIN inventory_items i
                ON bi.inventory_item_id = i.item_id
            WHERE bi.bom_id = ?
            ORDER BY i.item_name
            """,
            (bom_id,)
        ).fetchall()

        return {
            "bom": dict(bom),
            "components": [dict(row) for row in components]
        }

    finally:
        conn.close()