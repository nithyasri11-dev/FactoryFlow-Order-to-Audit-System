import sqlite3
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from database import get_connection


# =====================================================
# QUANTITY CONVERSION
# =====================================================

def quantity_to_milli(quantity, allow_zero=False):

    try:
        value = Decimal(str(quantity))

    except (InvalidOperation, ValueError):
        raise ValueError("Enter a valid quantity.")

    if not value.is_finite():
        raise ValueError("Quantity must be finite.")

    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError("Quantity must be positive.")

    scaled = value * 1000

    if scaled != scaled.to_integral_value():
        raise ValueError(
            "Maximum three decimal places are allowed."
        )

    return int(scaled)


def calculate_variance(planned, actual):

    if planned == 0:
        return Decimal("0")

    variance = (
        (Decimal(actual) - Decimal(planned))
        / Decimal(planned)
    ) * 100

    return variance.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP
    )


# =====================================================
# GET ACTIVE BOMS
# =====================================================

def get_active_boms():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                b.bom_id,
                b.product_id,
                b.version,
                b.expected_yield_packets,
                p.product_name,
                p.pack_size_g

            FROM boms b

            JOIN products p
                ON b.product_id = p.product_id

            WHERE b.active = 1

            ORDER BY p.product_name
            """
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


# =====================================================
# GET BOM RECIPE
# =====================================================

def get_bom_recipe(bom_id):

    conn = get_connection()

    try:

        bom = conn.execute(
            """
            SELECT
                b.bom_id,
                b.product_id,
                b.version,
                b.expected_yield_packets,
                p.product_name,
                p.pack_size_g,
                p.inventory_item_id AS finished_item_id

            FROM boms b

            JOIN products p
                ON b.product_id = p.product_id

            WHERE b.bom_id = ?
              AND b.active = 1
            """,
            (bom_id,)
        ).fetchone()

        if not bom:
            return None

        components = conn.execute(
            """
            SELECT
                bi.inventory_item_id,
                bi.quantity_per_batch_milli,
                i.item_code,
                i.item_name,
                i.base_unit,
                i.category

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
            "components": [
                dict(component)
                for component in components
            ]
        }

    finally:
        conn.close()


# =====================================================
# POST PRODUCTION RUN
# =====================================================

def post_production_run(
    bom_id,
    batch_count,
    actual_consumptions,
    actual_good_packets,
    damaged_pouches,
    cartons_used,
    user_id,
    tolerance_percent=3
):

    """
    Record and post a production run.

    actual_consumptions format:

    {
        inventory_item_id: actual_quantity,
        ...
    }

    Quantities are entered in each inventory item's
    registered base unit.

    The function:
    1. Checks BOM and stock.
    2. Creates production run.
    3. Records planned and actual consumption.
    4. Deducts raw materials and packaging.
    5. Adds finished goods.
    6. Calculates production variances.
    7. Records an audit log.

    All database changes occur in one transaction.
    """

    # -------------------------------------------------
    # INPUT VALIDATION
    # -------------------------------------------------

    try:

        batch_count = int(batch_count)

        actual_good_packets = int(actual_good_packets)

        damaged_pouches = int(damaged_pouches)

        cartons_used = int(cartons_used)

    except (ValueError, TypeError):

        raise ValueError(
            "Batch count and output quantities must be integers."
        )

    if batch_count <= 0:
        raise ValueError("Batch count must be positive.")

    if actual_good_packets < 0:
        raise ValueError("Output cannot be negative.")

    if damaged_pouches < 0 or cartons_used < 0:
        raise ValueError("Damaged pouches and cartons cannot be negative.")

    # -------------------------------------------------
    # CONNECT AND START TRANSACTION
    # -------------------------------------------------

    conn = get_connection()

    try:

        conn.execute("BEGIN IMMEDIATE")

        # ---------------------------------------------
        # VERIFY BOM
        # ---------------------------------------------

        bom = conn.execute(
            """
            SELECT
                b.bom_id,
                b.product_id,
                b.expected_yield_packets,
                p.product_name,
                p.inventory_item_id AS finished_item_id

            FROM boms b

            JOIN products p
                ON b.product_id = p.product_id

            WHERE b.bom_id = ?
              AND b.active = 1
            """,
            (bom_id,)
        ).fetchone()

        if not bom:

            raise ValueError(
                "The selected BOM does not exist or is inactive."
            )

        # ---------------------------------------------
        # LOAD BOM COMPONENTS
        # ---------------------------------------------

        components = conn.execute(
            """
            SELECT
                bi.inventory_item_id,
                bi.quantity_per_batch_milli,
                i.item_name,
                i.base_unit,
                i.active

            FROM bom_items bi

            JOIN inventory_items i
                ON bi.inventory_item_id = i.item_id

            WHERE bi.bom_id = ?
            """,
            (bom_id,)
        ).fetchall()

        if not components:

            raise ValueError(
                "The selected BOM contains no materials."
            )

        component_ids = {
            int(component["inventory_item_id"])
            for component in components
        }

        try:

            entered_ids = {
                int(item_id)
                for item_id in actual_consumptions.keys()
            }

        except (TypeError, ValueError):

            raise ValueError(
                "Invalid inventory item in actual consumption."
            )

        if component_ids != entered_ids:

            raise ValueError(
                "Actual consumption must be entered for every "
                "BOM component, with no extra items."
            )

        # ---------------------------------------------
        # CALCULATE EXPECTED OUTPUT
        # ---------------------------------------------

        expected_output = (
            int(bom["expected_yield_packets"])
            * batch_count
        )

        # ---------------------------------------------
        # PREPARE MATERIAL CONSUMPTION
        # ---------------------------------------------

        processed_materials = []

        for component in components:

            item_id = int(
                component["inventory_item_id"]
            )

            if not component["active"]:

                raise ValueError(
                    f"{component['item_name']} is inactive."
                )

            planned_quantity_milli = (
                int(component["quantity_per_batch_milli"])
                * batch_count
            )

            actual_quantity_milli = quantity_to_milli(
                actual_consumptions[item_id],
                allow_zero=True
            )

            # Get current stock from movement ledger.

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
                (item_id,)
            ).fetchone()

            available_stock = int(stock_row["balance"])

            if available_stock < actual_quantity_milli:

                raise ValueError(
                    f"Insufficient stock for {component['item_name']}. "
                    f"Available: {available_stock / 1000:.3f} "
                    f"{component['base_unit']}; "
                    f"Required: {actual_quantity_milli / 1000:.3f} "
                    f"{component['base_unit']}."
                )

            processed_materials.append({

                "item_id": item_id,

                "item_name": component["item_name"],

                "base_unit": component["base_unit"],

                "planned": planned_quantity_milli,

                "actual": actual_quantity_milli

            })

        # ---------------------------------------------
        # CREATE PRODUCTION RUN
        # ---------------------------------------------

        cursor = conn.execute(
            """
            INSERT INTO production_runs
            (
                product_id,
                bom_id,
                batch_count_milli,
                expected_output_packets,
                actual_good_packets,
                damaged_pouches,
                cartons_used,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'completed')
            """,
            (
                bom["product_id"],
                bom_id,
                batch_count * 1000,
                expected_output,
                actual_good_packets,
                damaged_pouches,
                cartons_used
            )
        )

        run_id = cursor.lastrowid

        # ---------------------------------------------
        # RECORD CONSUMPTION AND DEDUCT STOCK
        # ---------------------------------------------

        variance_results = []

        for material in processed_materials:

            planned = material["planned"]

            actual = material["actual"]

            variance = calculate_variance(
                planned,
                actual
            )

            flagged = abs(variance) > Decimal(
                str(tolerance_percent)
            )

            # Save consumption record.

            conn.execute(
                """
                INSERT INTO production_consumptions
                (
                    run_id,
                    inventory_item_id,
                    planned_quantity_milli,
                    actual_quantity_milli,
                    unit_rate_paise,
                    total_cost_paise
                )
                VALUES (?, ?, ?, ?, 0, 0)
                """,
                (
                    run_id,
                    material["item_id"],
                    planned,
                    actual
                )
            )

            # Deduct actual stock from the stock ledger.

            if actual > 0:

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
                        material["item_id"],
                        -actual,
                        "production_issue",
                        "production",
                        run_id,
                        user_id,
                        "Material issued to production"
                    )
                )

            variance_results.append({

                "item_name": material["item_name"],

                "planned_quantity": planned / 1000,

                "actual_quantity": actual / 1000,

                "unit": material["base_unit"],

                "variance_percent": float(variance),

                "flagged": flagged

            })

        # ---------------------------------------------
        # ADD FINISHED GOODS TO STOCK
        # ---------------------------------------------

        finished_item_id = int(
            bom["finished_item_id"]
        )

        if actual_good_packets > 0:

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
                    finished_item_id,
                    actual_good_packets * 1000,
                    "production_output",
                    "production",
                    run_id,
                    user_id,
                    "Finished goods received from production"
                )
            )

        # ---------------------------------------------
        # CALCULATE YIELD VARIANCE
        # ---------------------------------------------

        yield_variance = calculate_variance(
            expected_output,
            actual_good_packets
        )

        yield_flagged = (
            abs(yield_variance)
            > Decimal(str(tolerance_percent))
        )

        # ---------------------------------------------
        # RECORD AUDIT LOG
        # ---------------------------------------------

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
                user_id,
                "PRODUCTION_COMPLETED",
                "production_run",
                run_id,
                (
                    f"Expected output: {expected_output}; "
                    f"Actual output: {actual_good_packets}; "
                    f"Yield variance: {yield_variance}%"
                )
            )
        )

        # ---------------------------------------------
        # COMMIT ALL OPERATIONS
        # ---------------------------------------------

        conn.commit()

        return {

            "run_id": run_id,

            "product_name": bom["product_name"],

            "expected_output": expected_output,

            "actual_output": actual_good_packets,

            "damaged_pouches": damaged_pouches,

            "cartons_used": cartons_used,

            "yield_variance_percent": float(
                yield_variance
            ),

            "yield_flagged": yield_flagged,

            "materials": variance_results

        }

    except Exception:

        conn.rollback()

        raise

    finally:

        conn.close()


# =====================================================
# PRODUCTION HISTORY
# =====================================================

def get_production_runs():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT
                r.run_id,
                r.product_id,
                r.bom_id,
                r.batch_count_milli,
                r.expected_output_packets,
                r.actual_good_packets,
                r.damaged_pouches,
                r.cartons_used,
                r.status,
                r.production_date,
                p.product_name

            FROM production_runs r

            JOIN products p
                ON r.product_id = p.product_id

            ORDER BY r.run_id DESC
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            if data["actual_good_packets"] is not None:

                variance = calculate_variance(
                    data["expected_output_packets"],
                    data["actual_good_packets"]
                )

                data["yield_variance_percent"] = float(
                    variance
                )

            else:

                data["yield_variance_percent"] = None

            result.append(data)

        return result

    finally:
        conn.close()


# =====================================================
# PRODUCTION RUN DETAILS
# =====================================================

def get_production_run_details(run_id):

    conn = get_connection()

    try:

        run = conn.execute(
            """
            SELECT
                r.*,
                p.product_name

            FROM production_runs r

            JOIN products p
                ON r.product_id = p.product_id

            WHERE r.run_id = ?
            """,
            (run_id,)
        ).fetchone()

        if not run:
            return None

        materials = conn.execute(
            """
            SELECT
                pc.inventory_item_id,
                i.item_name,
                i.base_unit,
                pc.planned_quantity_milli,
                pc.actual_quantity_milli

            FROM production_consumptions pc

            JOIN inventory_items i
                ON pc.inventory_item_id = i.item_id

            WHERE pc.run_id = ?
            """,
            (run_id,)
        ).fetchall()

        material_results = []

        for material in materials:

            data = dict(material)

            planned = data["planned_quantity_milli"]

            actual = data["actual_quantity_milli"]

            data["planned_quantity"] = planned / 1000

            data["actual_quantity"] = actual / 1000

            data["variance_percent"] = float(
                calculate_variance(planned, actual)
            )

            material_results.append(data)

        return {

            "run": dict(run),

            "materials": material_results

        }

    finally:
        conn.close()