import sqlite3
from decimal import Decimal, InvalidOperation

from database import get_connection


def quantity_to_milli(value):
    """Convert a quantity into thousandths of its base unit."""

    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Enter a valid quantity.")

    if not number.is_finite() or number < 0:
        raise ValueError("Quantity cannot be negative.")

    scaled = number * 1000

    if scaled != scaled.to_integral_value():
        raise ValueError("Maximum three decimal places are allowed.")

    return int(scaled)


def rupees_to_paise(value):
    """Convert rupees into integer paise."""

    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Enter a valid price.")

    if not amount.is_finite() or amount < 0:
        raise ValueError("Price cannot be negative.")

    scaled = amount * 100

    if scaled != scaled.to_integral_value():
        raise ValueError("Maximum two decimal places are allowed.")

    return int(scaled)


def create_customer(name, customer_type, state, gstin="", phone=""):
    name = name.strip()
    state = state.strip()

    if not name or not state:
        raise ValueError("Customer name and state are required.")

    if customer_type not in ["Retailer", "Distributor"]:
        raise ValueError("Invalid customer type.")

    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO customers
            (customer_name, customer_type, state, gstin, phone)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, customer_type, state, gstin.strip(), phone.strip())
        )

        conn.commit()
        return cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("Unable to add customer.")

    finally:
        conn.close()


def create_supplier(name, state, gstin="", phone=""):
    name = name.strip()
    state = state.strip()

    if not name or not state:
        raise ValueError("Supplier name and state are required.")

    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO suppliers
            (supplier_name, state, gstin, phone)
            VALUES (?, ?, ?, ?)
            """,
            (name, state, gstin.strip(), phone.strip())
        )

        conn.commit()
        return cursor.lastrowid

    finally:
        conn.close()


def create_inventory_item(
    item_code,
    item_name,
    category,
    base_unit,
    reorder_level=0
):
    item_code = item_code.strip().upper()
    item_name = item_name.strip()

    if not item_code or not item_name:
        raise ValueError("Item code and item name are required.")

    if category not in ["raw_material", "packaging_material"]:
        raise ValueError("Invalid inventory category.")

    if base_unit not in ["kg", "g", "litre", "piece"]:
        raise ValueError("Invalid unit.")

    reorder_milli = quantity_to_milli(reorder_level)

    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO inventory_items
            (
                item_code,
                item_name,
                category,
                base_unit,
                reorder_level_milli
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item_code,
                item_name,
                category,
                base_unit,
                reorder_milli
            )
        )

        conn.commit()
        return cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("This inventory item code already exists.")

    finally:
        conn.close()


def create_finished_product(
    product_name,
    item_code,
    pack_size_g,
    selling_price,
    gst_percent,
    hsn_code=""
):
    product_name = product_name.strip()
    item_code = item_code.strip().upper()

    if not product_name or not item_code:
        raise ValueError("Product name and item code are required.")

    if int(pack_size_g) <= 0:
        raise ValueError("Pack size must be positive.")

    price_paise = rupees_to_paise(selling_price)
    gst = Decimal(str(gst_percent))

    if not gst.is_finite() or gst < 0 or gst > 100:
        raise ValueError("Invalid GST rate.")

    if (gst * 100) != (gst * 100).to_integral_value():
        raise ValueError("GST rate supports up to two decimal places.")

    gst_bps = int(gst * 100)

    conn = get_connection()

    try:
        cursor = conn.execute(
            """
            INSERT INTO inventory_items
            (item_code, item_name, category, base_unit)
            VALUES (?, ?, 'finished_good', 'piece')
            """,
            (item_code, product_name)
        )

        inventory_item_id = cursor.lastrowid

        cursor = conn.execute(
            """
            INSERT INTO products
            (
                inventory_item_id,
                product_name,
                pack_size_g,
                selling_price_paise,
                gst_rate_bps,
                hsn_code
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                inventory_item_id,
                product_name,
                int(pack_size_g),
                price_paise,
                gst_bps,
                hsn_code.strip()
            )
        )

        conn.commit()
        return cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.rollback()
        raise ValueError("This product or item code already exists.")

    finally:
        conn.close()


def fetch_records(query):
    conn = get_connection()

    try:
        rows = conn.execute(query).fetchall()
        return [dict(row) for row in rows]

    finally:
        conn.close()


def get_customers():
    return fetch_records(
        """
        SELECT customer_id, customer_name,
               customer_type, state, gstin, phone
        FROM customers
        ORDER BY customer_name
        """
    )


def get_suppliers():
    return fetch_records(
        """
        SELECT supplier_id, supplier_name,
               state, gstin, phone
        FROM suppliers
        ORDER BY supplier_name
        """
    )


def get_inventory_items():
    return fetch_records(
        """
        SELECT item_id, item_code, item_name,
               category, base_unit, reorder_level_milli
        FROM inventory_items
        ORDER BY item_code
        """
    )


def get_products():
    return fetch_records(
        """
        SELECT
            p.product_id,
            p.product_name,
            p.pack_size_g,
            p.selling_price_paise,
            p.gst_rate_bps,
            p.hsn_code,
            i.item_code
        FROM products p
        JOIN inventory_items i
        ON p.inventory_item_id = i.item_id
        ORDER BY p.product_name
        """
    )