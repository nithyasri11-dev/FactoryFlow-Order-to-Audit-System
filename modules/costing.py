from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from database import get_connection


# ============================================================
# 1. MONEY CONVERSION
# ============================================================

def rupees_to_paise(value, allow_zero=False):

    try:
        amount = Decimal(str(value))

    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid amount.")

    if not amount.is_finite():
        raise ValueError("Amount must be finite.")

    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError("Amount cannot be negative or zero.")

    amount = amount.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return int(amount * 100)


def paise_to_rupees(value):

    return (
        Decimal(int(value)) / Decimal(100)
    ).quantize(Decimal("0.01"))


def calculate_cost_per_packet(total_cost_paise, packets):

    if packets <= 0:
        raise ValueError(
            "Production output must be greater than zero."
        )

    return (
        Decimal(total_cost_paise)
        / Decimal(packets)
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# 2. INITIALIZE COSTING TABLES
# ============================================================

def initialize_costing_tables():

    conn = get_connection()

    try:

        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS inventory_cost_rates (

                inventory_item_id INTEGER PRIMARY KEY,

                standard_rate_paise INTEGER NOT NULL,

                updated_by INTEGER NOT NULL,

                notes TEXT,

                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (inventory_item_id)
                    REFERENCES inventory_items(item_id),

                FOREIGN KEY (updated_by)
                    REFERENCES users(user_id)

            );


            CREATE TABLE IF NOT EXISTS production_cost_records (

                costing_id INTEGER PRIMARY KEY AUTOINCREMENT,

                run_id INTEGER NOT NULL UNIQUE,

                material_cost_paise INTEGER NOT NULL DEFAULT 0,

                labour_cost_paise INTEGER NOT NULL DEFAULT 0,

                electricity_cost_paise INTEGER NOT NULL DEFAULT 0,

                other_overhead_paise INTEGER NOT NULL DEFAULT 0,

                total_production_cost_paise INTEGER NOT NULL DEFAULT 0,

                good_packets INTEGER NOT NULL,

                cost_per_packet_paise INTEGER NOT NULL,

                created_by INTEGER NOT NULL,

                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (run_id)
                    REFERENCES production_runs(run_id),

                FOREIGN KEY (created_by)
                    REFERENCES users(user_id)

            );


            CREATE TABLE IF NOT EXISTS production_cost_items (

                cost_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

                costing_id INTEGER NOT NULL,

                inventory_item_id INTEGER NOT NULL,

                actual_quantity_milli INTEGER NOT NULL,

                unit_rate_paise INTEGER NOT NULL,

                total_cost_paise INTEGER NOT NULL,

                FOREIGN KEY (costing_id)
                    REFERENCES production_cost_records(costing_id),

                FOREIGN KEY (inventory_item_id)
                    REFERENCES inventory_items(item_id)

            );


            CREATE INDEX IF NOT EXISTS idx_production_cost_run

            ON production_cost_records(run_id);


            CREATE INDEX IF NOT EXISTS idx_production_cost_items

            ON production_cost_items(costing_id);

            """
        )

        conn.commit()

    finally:

        conn.close()


# ============================================================
# 3. SET STANDARD INVENTORY COST
# ============================================================

def set_inventory_cost_rate(
    inventory_item_id,
    standard_rate_rupees,
    updated_by,
    notes="",
):

    """
    Set the standard cost per base unit.

    This rate is used when historical purchase information
    is unavailable for an inventory item.

    Purchase-weighted average cost takes priority when
    purchase records exist before the production date.
    """

    rate_paise = rupees_to_paise(
        standard_rate_rupees
    )

    conn = get_connection()

    try:

        item = conn.execute(
            """
            SELECT item_id

            FROM inventory_items

            WHERE item_id = ?
            """,
            (inventory_item_id,),
        ).fetchone()

        if not item:

            raise ValueError(
                "Inventory item does not exist."
            )

        conn.execute(
            """
            INSERT INTO inventory_cost_rates
            (
                inventory_item_id,
                standard_rate_paise,
                updated_by,
                notes,
                updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)

            ON CONFLICT(inventory_item_id)

            DO UPDATE SET

                standard_rate_paise = excluded.standard_rate_paise,

                updated_by = excluded.updated_by,

                notes = excluded.notes,

                updated_at = CURRENT_TIMESTAMP
            """,
            (
                inventory_item_id,
                rate_paise,
                updated_by,
                notes,
            ),
        )

        conn.commit()

        return True

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# 4. GET INVENTORY COST RATES
# ============================================================

def get_inventory_cost_rates():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                i.item_id,
                i.item_code,
                i.item_name,
                i.base_unit,
                r.standard_rate_paise,
                r.notes,
                r.updated_at

            FROM inventory_items i

            LEFT JOIN inventory_cost_rates r

                ON i.item_id = r.inventory_item_id

            ORDER BY i.item_name
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            if data["standard_rate_paise"] is not None:

                data["standard_rate_rupees"] = float(
                    paise_to_rupees(
                        data["standard_rate_paise"]
                    )
                )

            else:

                data["standard_rate_rupees"] = None

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 5. GET HISTORICAL PURCHASE-WEIGHTED AVERAGE COST
# ============================================================

def get_weighted_average_purchase_cost(
    inventory_item_id,
    production_date,
):

    """
    Calculate weighted-average purchase rate up to the
    production date.

    Formula:

    Total purchase value / Total purchased quantity.

    The rate is returned in paise per base unit.

    If purchase data is unavailable, the configured
    standard inventory rate is used.
    """

    conn = get_connection()

    try:

        purchase_data = conn.execute(
            """
            SELECT

                SUM(
                    pi.quantity_milli * pi.unit_rate_paise
                ) AS weighted_value,

                SUM(
                    pi.quantity_milli
                ) AS total_quantity

            FROM purchase_items pi

            JOIN purchases p

                ON pi.purchase_id = p.purchase_id

            WHERE pi.inventory_item_id = ?

              AND p.purchase_date <= ?

            """,
            (
                inventory_item_id,
                production_date,
            ),
        ).fetchone()

        total_quantity = int(
            purchase_data["total_quantity"] or 0
        )

        if total_quantity > 0:

            weighted_value = Decimal(
                int(purchase_data["weighted_value"])
            )

            average_rate = (
                weighted_value / Decimal(total_quantity)
            ).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )

            return int(average_rate), "purchase_average"

        # Use configured standard rate if there are no
        # historical purchase records.

        standard = conn.execute(
            """
            SELECT standard_rate_paise

            FROM inventory_cost_rates

            WHERE inventory_item_id = ?
            """,
            (inventory_item_id,),
        ).fetchone()

        if standard:

            return (
                int(standard["standard_rate_paise"]),
                "standard_rate",
            )

        return None, "missing"

    finally:

        conn.close()


# ============================================================
# 6. GET PRODUCTION RUNS NOT YET COSTED
# ============================================================

def get_uncosted_production_runs():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                r.run_id,
                r.product_id,
                r.bom_id,
                r.production_date,
                r.expected_output_packets,
                r.actual_good_packets,
                r.status,
                p.product_name,
                p.pack_size_g

            FROM production_runs r

            JOIN products p

                ON r.product_id = p.product_id

            LEFT JOIN production_cost_records c

                ON r.run_id = c.run_id

            WHERE r.status = 'completed'

              AND c.costing_id IS NULL

            ORDER BY r.run_id DESC
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# ============================================================
# 7. GET PRODUCTION RUN MATERIALS
# ============================================================

def get_production_run_materials(run_id):

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                pc.inventory_item_id,
                pc.planned_quantity_milli,
                pc.actual_quantity_milli,
                i.item_code,
                i.item_name,
                i.base_unit

            FROM production_consumptions pc

            JOIN inventory_items i

                ON pc.inventory_item_id = i.item_id

            WHERE pc.run_id = ?

            ORDER BY i.item_name
            """,
            (run_id,),
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]

    finally:

        conn.close()


# ============================================================
# 8. CREATE PRODUCTION COST RECORD
# ============================================================

def create_production_costing(
    run_id,
    labour_cost,
    electricity_cost,
    other_overhead,
    created_by,
):

    """
    Calculate total manufacturing cost for a production run.

    Total Production Cost =

    Raw Material Cost
    + Packaging Material Cost
    + Labour Cost
    + Electricity Cost
    + Other Manufacturing Overheads

    Cost Per Packet =

    Total Production Cost / Actual Good Packets
    """

    labour_paise = rupees_to_paise(
        labour_cost,
        allow_zero=True,
    )

    electricity_paise = rupees_to_paise(
        electricity_cost,
        allow_zero=True,
    )

    other_paise = rupees_to_paise(
        other_overhead,
        allow_zero=True,
    )

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # ----------------------------------------------------
        # VERIFY PRODUCTION RUN
        # ----------------------------------------------------

        run = conn.execute(
            """
            SELECT
                run_id,
                product_id,
                production_date,
                actual_good_packets,
                status

            FROM production_runs

            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

        if not run:

            raise ValueError(
                "Production run does not exist."
            )

        if run["status"] != "completed":

            raise ValueError(
                "Only completed production runs can be costed."
            )

        good_packets = int(
            run["actual_good_packets"]
        )

        if good_packets <= 0:

            raise ValueError(
                "Actual good production must be greater than zero."
            )

        # ----------------------------------------------------
        # PREVENT DUPLICATE COST RECORDS
        # ----------------------------------------------------

        existing = conn.execute(
            """
            SELECT costing_id

            FROM production_cost_records

            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()

        if existing:

            raise ValueError(
                "Costing has already been completed for this production run."
            )

        # ----------------------------------------------------
        # LOAD MATERIAL CONSUMPTION
        # ----------------------------------------------------

        materials = conn.execute(
            """
            SELECT
                pc.inventory_item_id,
                pc.actual_quantity_milli,
                pc.planned_quantity_milli,
                i.item_name

            FROM production_consumptions pc

            JOIN inventory_items i

                ON pc.inventory_item_id = i.item_id

            WHERE pc.run_id = ?
            """,
            (run_id,),
        ).fetchall()

        if not materials:

            raise ValueError(
                "No material consumption records found."
            )

        material_cost_paise = 0

        processed_materials = []

        for material in materials:

            item_id = int(
                material["inventory_item_id"]
            )

            actual_quantity = int(
                material["actual_quantity_milli"]
            )

            if actual_quantity < 0:

                raise ValueError(
                    f"Invalid consumption quantity for {material['item_name']}."
                )

            if actual_quantity == 0:

                rate_paise, source = (
                    get_weighted_average_purchase_cost(
                        item_id,
                        run["production_date"],
                    )
                )

                # No cost is incurred for zero consumption.

                if rate_paise is None:
                    rate_paise = 0

                item_cost_paise = 0

            else:

                rate_paise, source = (
                    get_weighted_average_purchase_cost(
                        item_id,
                        run["production_date"],
                    )
                )

                if rate_paise is None:

                    raise ValueError(
                        f"Cost rate missing for {material['item_name']}. "
                        "Enter its standard cost in Inventory Cost Rates."
                    )

                # Quantity is stored in thousandths of
                # the registered base unit.

                item_cost = (
                    Decimal(actual_quantity)
                    * Decimal(rate_paise)
                    / Decimal(1000)
                )

                item_cost_paise = int(
                    item_cost.quantize(
                        Decimal("1"),
                        rounding=ROUND_HALF_UP,
                    )
                )

            material_cost_paise += item_cost_paise

            processed_materials.append({

                "inventory_item_id": item_id,

                "item_name": material["item_name"],

                "actual_quantity_milli": actual_quantity,

                "planned_quantity_milli": int(
                    material["planned_quantity_milli"]
                ),

                "unit_rate_paise": int(rate_paise),

                "total_cost_paise": item_cost_paise,

                "cost_source": source,

            })

        # ----------------------------------------------------
        # CALCULATE TOTAL COST
        # ----------------------------------------------------

        total_cost = (
            material_cost_paise
            + labour_paise
            + electricity_paise
            + other_paise
        )

        cost_per_packet = calculate_cost_per_packet(
            total_cost,
            good_packets,
        )

        # ----------------------------------------------------
        # CREATE COST HEADER
        # ----------------------------------------------------

        cursor = conn.execute(
            """
            INSERT INTO production_cost_records
            (
                run_id,
                material_cost_paise,
                labour_cost_paise,
                electricity_cost_paise,
                other_overhead_paise,
                total_production_cost_paise,
                good_packets,
                cost_per_packet_paise,
                created_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                material_cost_paise,
                labour_paise,
                electricity_paise,
                other_paise,
                total_cost,
                good_packets,
                int(cost_per_packet),
                created_by,
            ),
        )

        costing_id = cursor.lastrowid

        # ----------------------------------------------------
        # CREATE MATERIAL COST DETAILS
        # ----------------------------------------------------

        for material in processed_materials:

            conn.execute(
                """
                INSERT INTO production_cost_items
                (
                    costing_id,
                    inventory_item_id,
                    actual_quantity_milli,
                    unit_rate_paise,
                    total_cost_paise
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    costing_id,
                    material["inventory_item_id"],
                    material["actual_quantity_milli"],
                    material["unit_rate_paise"],
                    material["total_cost_paise"],
                ),
            )

            # Update the production consumption record
            # with its calculated material cost.

            conn.execute(
                """
                UPDATE production_consumptions

                SET
                    unit_rate_paise = ?,
                    total_cost_paise = ?

                WHERE run_id = ?

                  AND inventory_item_id = ?
                """,
                (
                    material["unit_rate_paise"],
                    material["total_cost_paise"],
                    run_id,
                    material["inventory_item_id"],
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
                "PRODUCTION_COSTING_COMPLETED",
                "production_cost",
                costing_id,
                (
                    f"Production run {run_id} costed. "
                    f"Total production cost: "
                    f"₹{paise_to_rupees(total_cost)}. "
                    f"Cost per packet: "
                    f"₹{paise_to_rupees(int(cost_per_packet))}."
                ),
            ),
        )

        conn.commit()

        return {

            "costing_id": costing_id,

            "run_id": run_id,

            "material_cost_paise": material_cost_paise,

            "labour_cost_paise": labour_paise,

            "electricity_cost_paise": electricity_paise,

            "other_overhead_paise": other_paise,

            "total_cost_paise": total_cost,

            "good_packets": good_packets,

            "cost_per_packet_paise": int(
                cost_per_packet
            ),

            "total_cost_rupees": paise_to_rupees(
                total_cost
            ),

            "cost_per_packet_rupees": paise_to_rupees(
                int(cost_per_packet)
            ),

        }

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# ============================================================
# 9. GET PRODUCTION COST REGISTER
# ============================================================

def get_production_cost_register():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                c.costing_id,
                c.run_id,
                c.material_cost_paise,
                c.labour_cost_paise,
                c.electricity_cost_paise,
                c.other_overhead_paise,
                c.total_production_cost_paise,
                c.good_packets,
                c.cost_per_packet_paise,
                c.created_at,

                p.product_name,

                r.production_date

            FROM production_cost_records c

            JOIN production_runs r

                ON c.run_id = r.run_id

            JOIN products p

                ON r.product_id = p.product_id

            ORDER BY c.costing_id DESC
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["material_cost_rupees"] = float(
                paise_to_rupees(
                    data["material_cost_paise"]
                )
            )

            data["labour_cost_rupees"] = float(
                paise_to_rupees(
                    data["labour_cost_paise"]
                )
            )

            data["electricity_cost_rupees"] = float(
                paise_to_rupees(
                    data["electricity_cost_paise"]
                )
            )

            data["other_overhead_rupees"] = float(
                paise_to_rupees(
                    data["other_overhead_paise"]
                )
            )

            data["total_cost_rupees"] = float(
                paise_to_rupees(
                    data["total_production_cost_paise"]
                )
            )

            data["cost_per_packet_rupees"] = float(
                paise_to_rupees(
                    data["cost_per_packet_paise"]
                )
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 10. GET PRODUCTION COST DETAILS
# ============================================================

def get_production_cost_details(costing_id):

    conn = get_connection()

    try:

        record = conn.execute(
            """
            SELECT
                c.*,
                r.production_date,
                r.product_id,
                p.product_name

            FROM production_cost_records c

            JOIN production_runs r

                ON c.run_id = r.run_id

            JOIN products p

                ON r.product_id = p.product_id

            WHERE c.costing_id = ?
            """,
            (costing_id,),
        ).fetchone()

        if not record:

            return None

        materials = conn.execute(
            """
            SELECT
                ci.inventory_item_id,
                i.item_name,
                i.base_unit,
                ci.actual_quantity_milli,
                ci.unit_rate_paise,
                ci.total_cost_paise

            FROM production_cost_items ci

            JOIN inventory_items i

                ON ci.inventory_item_id = i.item_id

            WHERE ci.costing_id = ?

            ORDER BY i.item_name
            """,
            (costing_id,),
        ).fetchall()

        record_data = dict(record)

        money_fields = [
            "material_cost_paise",
            "labour_cost_paise",
            "electricity_cost_paise",
            "other_overhead_paise",
            "total_production_cost_paise",
            "cost_per_packet_paise",
        ]

        for field in money_fields:

            record_data[
                field.replace("_paise", "_rupees")
            ] = float(
                paise_to_rupees(
                    record_data[field]
                )
            )

        material_results = []

        for material in materials:

            data = dict(material)

            data["actual_quantity"] = (
                data["actual_quantity_milli"] / 1000
            )

            data["unit_rate_rupees"] = float(
                paise_to_rupees(
                    data["unit_rate_paise"]
                )
            )

            data["total_cost_rupees"] = float(
                paise_to_rupees(
                    data["total_cost_paise"]
                )
            )

            material_results.append(data)

        return {

            "record": record_data,

            "materials": material_results,

        }

    finally:

        conn.close()


# ============================================================
# 11. PRODUCT-WISE PROFITABILITY REPORT
# ============================================================

def get_product_profitability():

    """
    Calculates product-wise:

    Average production cost per packet.
    Average invoiced taxable selling price.
    Gross profit per packet.
    Gross profit margin.

    Production cost is averaged using completed cost records.

    Sales revenue excludes GST because it uses taxable values.
    """

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                p.product_id,

                p.product_name,

                COALESCE(
                    production.total_cost_paise,
                    0
                ) AS production_cost_paise,

                COALESCE(
                    production.total_packets,
                    0
                ) AS produced_packets,

                COALESCE(
                    sales.total_revenue_paise,
                    0
                ) AS revenue_paise,

                COALESCE(
                    sales.sold_packets,
                    0
                ) AS sold_packets

            FROM products p

            LEFT JOIN (

                SELECT

                    r.product_id,

                    SUM(c.total_production_cost_paise)
                        AS total_cost_paise,

                    SUM(c.good_packets)
                        AS total_packets

                FROM production_cost_records c

                JOIN production_runs r

                    ON c.run_id = r.run_id

                GROUP BY r.product_id

            ) production

                ON p.product_id = production.product_id

            LEFT JOIN (

                SELECT

                    ii.product_id,

                    SUM(ii.taxable_value_paise)
                        AS total_revenue_paise,

                    SUM(ii.quantity_packets)
                        AS sold_packets

                FROM invoice_items ii

                JOIN invoice_headers ih

                    ON ii.invoice_id = ih.invoice_id

                WHERE ih.status = 'issued'

                GROUP BY ii.product_id

            ) sales

                ON p.product_id = sales.product_id

            ORDER BY p.product_name
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            produced = int(
                data["produced_packets"]
            )

            sold = int(
                data["sold_packets"]
            )

            production_cost = int(
                data["production_cost_paise"]
            )

            revenue = int(
                data["revenue_paise"]
            )

            if produced > 0:

                average_cost = (
                    Decimal(production_cost)
                    / Decimal(produced)
                )

            else:

                average_cost = None

            if sold > 0:

                average_selling_price = (
                    Decimal(revenue)
                    / Decimal(sold)
                )

            else:

                average_selling_price = None

            if (
                average_cost is not None
                and average_selling_price is not None
            ):

                gross_profit = (
                    average_selling_price - average_cost
                )

                if average_selling_price > 0:

                    margin = (
                        gross_profit
                        / average_selling_price
                    ) * 100

                else:

                    margin = Decimal("0")

            else:

                gross_profit = None

                margin = None

            data["average_cost_per_packet_rupees"] = (
                float(
                    paise_to_rupees(
                        int(
                            average_cost.quantize(
                                Decimal("1"),
                                rounding=ROUND_HALF_UP,
                            )
                        )
                    )
                )
                if average_cost is not None
                else None
            )

            data["average_selling_price_rupees"] = (
                float(
                    paise_to_rupees(
                        int(
                            average_selling_price.quantize(
                                Decimal("1"),
                                rounding=ROUND_HALF_UP,
                            )
                        )
                    )
                )
                if average_selling_price is not None
                else None
            )

            data["gross_profit_per_packet_rupees"] = (
                float(
                    paise_to_rupees(
                        int(
                            gross_profit.quantize(
                                Decimal("1"),
                                rounding=ROUND_HALF_UP,
                            )
                        )
                    )
                )
                if gross_profit is not None
                else None
            )

            data["gross_profit_margin_percent"] = (
                float(
                    margin.quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                )
                if margin is not None
                else None
            )

            result.append(data)

        return result

    finally:

        conn.close()