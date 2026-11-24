import sqlite3
from io import BytesIO
from datetime import date

import pandas as pd

from database import get_connection
from modules.costing import get_product_profitability


# ============================================================
# 1. COMMON REPORT HELPERS
# ============================================================

def validate_date_range(start_date, end_date):

    try:

        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))

    except (ValueError, TypeError):

        raise ValueError("Invalid report date range.")

    if start > end:

        raise ValueError(
            "Start date cannot be after end date."
        )

    return start.isoformat(), end.isoformat()


def rows_to_dicts(rows):

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# 2. SALES REPORT
# ============================================================

def get_sales_report(start_date, end_date):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                ih.invoice_date,

                ih.invoice_number,

                ih.order_id,

                c.customer_name,

                ih.taxable_value_paise,

                ih.cgst_paise,

                ih.sgst_paise,

                ih.igst_paise,

                ih.total_tax_paise,

                ih.grand_total_paise,

                ih.payment_status

            FROM invoice_headers ih

            JOIN customers c

                ON ih.customer_id = c.customer_id

            WHERE ih.invoice_date BETWEEN ? AND ?

              AND ih.status = 'issued'

            ORDER BY
                ih.invoice_date,
                ih.invoice_id
            """,
            (
                start_date,
                end_date,
            ),
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["taxable_value_rupees"] = (
                data["taxable_value_paise"] / 100
            )

            data["cgst_rupees"] = (
                data["cgst_paise"] / 100
            )

            data["sgst_rupees"] = (
                data["sgst_paise"] / 100
            )

            data["igst_rupees"] = (
                data["igst_paise"] / 100
            )

            data["total_tax_rupees"] = (
                data["total_tax_paise"] / 100
            )

            data["grand_total_rupees"] = (
                data["grand_total_paise"] / 100
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 3. DAILY SALES SUMMARY
# ============================================================

def get_daily_sales_summary(start_date, end_date):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                invoice_date,

                COUNT(*) AS invoice_count,

                SUM(taxable_value_paise)
                    AS taxable_value_paise,

                SUM(total_tax_paise)
                    AS total_tax_paise,

                SUM(grand_total_paise)
                    AS grand_total_paise

            FROM invoice_headers

            WHERE invoice_date BETWEEN ? AND ?

              AND status = 'issued'

            GROUP BY invoice_date

            ORDER BY invoice_date
            """,
            (
                start_date,
                end_date,
            ),
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["taxable_value_rupees"] = (
                data["taxable_value_paise"] / 100
            )

            data["total_tax_rupees"] = (
                data["total_tax_paise"] / 100
            )

            data["grand_total_rupees"] = (
                data["grand_total_paise"] / 100
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 4. MONTHLY SALES SUMMARY
# ============================================================

def get_monthly_sales_summary(start_date, end_date):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                strftime('%Y-%m', invoice_date)
                    AS sales_month,

                COUNT(*) AS invoice_count,

                SUM(taxable_value_paise)
                    AS taxable_value_paise,

                SUM(total_tax_paise)
                    AS total_tax_paise,

                SUM(grand_total_paise)
                    AS grand_total_paise

            FROM invoice_headers

            WHERE invoice_date BETWEEN ? AND ?

              AND status = 'issued'

            GROUP BY sales_month

            ORDER BY sales_month
            """,
            (
                start_date,
                end_date,
            ),
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["taxable_value_rupees"] = (
                data["taxable_value_paise"] / 100
            )

            data["total_tax_rupees"] = (
                data["total_tax_paise"] / 100
            )

            data["grand_total_rupees"] = (
                data["grand_total_paise"] / 100
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 5. PURCHASE REPORT
# ============================================================

def get_purchase_report(start_date, end_date):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                p.purchase_id,

                p.purchase_date,

                p.invoice_reference,

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

            WHERE p.purchase_date BETWEEN ? AND ?

            GROUP BY
                p.purchase_id,
                p.purchase_date,
                p.invoice_reference,
                p.status,
                s.supplier_name

            ORDER BY p.purchase_date

            """,
            (
                start_date,
                end_date,
            ),
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


# ============================================================
# 6. INVENTORY POSITION REPORT
# ============================================================

def get_inventory_position_report():

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
                    SUM(sm.quantity_delta_milli),
                    0
                ) AS balance_milli

            FROM inventory_items i

            LEFT JOIN stock_movements sm

                ON i.item_id = sm.inventory_item_id

            GROUP BY

                i.item_id,
                i.item_code,
                i.item_name,
                i.category,
                i.base_unit,
                i.reorder_level_milli

            ORDER BY i.item_name
            """
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            balance = (
                data["balance_milli"] / 1000
            )

            reorder_level = (
                data["reorder_level_milli"] / 1000
            )

            if balance < 0:

                status = "Negative Stock"

            elif (
                reorder_level > 0
                and balance <= reorder_level
            ):

                status = "Low Stock"

            else:

                status = "Available"

            data["balance"] = balance

            data["reorder_level"] = reorder_level

            data["stock_status"] = status

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 7. STOCK MOVEMENT REPORT
# ============================================================

def get_inventory_movement_report(
    start_date,
    end_date,
    inventory_item_id=None,
):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        query = """
            SELECT

                sm.movement_id,

                sm.inventory_item_id,

                i.item_code,

                i.item_name,

                i.base_unit,

                sm.quantity_delta_milli,

                sm.movement_type,

                sm.source_type,

                sm.source_id,

                sm.notes,

                sm.created_by,

                sm.created_at,

                u.username

            FROM stock_movements sm

            JOIN inventory_items i

                ON sm.inventory_item_id = i.item_id

            LEFT JOIN users u

                ON sm.created_by = u.user_id

            WHERE date(sm.created_at) BETWEEN ? AND ?

        """

        params = [
            start_date,
            end_date,
        ]

        if inventory_item_id is not None:

            query += """
                AND sm.inventory_item_id = ?
            """

            params.append(inventory_item_id)

        query += """
            ORDER BY sm.created_at, sm.movement_id
        """

        rows = conn.execute(
            query,
            params,
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            data["quantity_change"] = (
                data["quantity_delta_milli"] / 1000
            )

            if data["quantity_change"] > 0:

                data["movement_direction"] = "IN"

            elif data["quantity_change"] < 0:

                data["movement_direction"] = "OUT"

            else:

                data["movement_direction"] = "ZERO"

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 8. PRODUCTION PERFORMANCE REPORT
# ============================================================

def get_production_performance_report(
    start_date,
    end_date,
):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                r.run_id,

                r.production_date,

                p.product_name,

                r.batch_count_milli,

                r.expected_output_packets,

                r.actual_good_packets,

                r.damaged_pouches,

                r.cartons_used,

                r.status

            FROM production_runs r

            JOIN products p

                ON r.product_id = p.product_id

            WHERE date(r.production_date) BETWEEN ? AND ?

            ORDER BY r.production_date, r.run_id
            """,
            (
                start_date,
                end_date,
            ),
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            expected = int(
                data["expected_output_packets"]
            )

            actual = int(
                data["actual_good_packets"]
            )

            if expected > 0:

                yield_variance = (
                    (actual - expected)
                    / expected
                ) * 100

            else:

                yield_variance = 0

            data["yield_variance_percent"] = round(
                yield_variance,
                2,
            )

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 9. MATERIAL CONSUMPTION VARIANCE REPORT
# ============================================================

def get_material_variance_report(
    start_date,
    end_date,
):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                r.run_id,

                r.production_date,

                p.product_name,

                i.item_code,

                i.item_name,

                i.base_unit,

                pc.planned_quantity_milli,

                pc.actual_quantity_milli

            FROM production_consumptions pc

            JOIN production_runs r

                ON pc.run_id = r.run_id

            JOIN products p

                ON r.product_id = p.product_id

            JOIN inventory_items i

                ON pc.inventory_item_id = i.item_id

            WHERE date(r.production_date) BETWEEN ? AND ?

            ORDER BY
                r.production_date,
                r.run_id,
                i.item_name
            """,
            (
                start_date,
                end_date,
            ),
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            planned = int(
                data["planned_quantity_milli"]
            )

            actual = int(
                data["actual_quantity_milli"]
            )

            variance = actual - planned

            if planned != 0:

                variance_percent = (
                    variance / planned
                ) * 100

            else:

                variance_percent = 0

            data["planned_quantity"] = planned / 1000

            data["actual_quantity"] = actual / 1000

            data["variance_quantity"] = variance / 1000

            data["variance_percent"] = round(
                variance_percent,
                2,
            )

            if variance > 0:

                data["variance_type"] = "Excess Consumption"

            elif variance < 0:

                data["variance_type"] = "Lower Consumption"

            else:

                data["variance_type"] = "No Variance"

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 10. GST SUMMARY REPORT
# ============================================================

def get_gst_summary_report(start_date, end_date):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                strftime('%Y-%m', invoice_date)
                    AS tax_period,

                supply_type,

                COUNT(*) AS invoice_count,

                SUM(taxable_value_paise)
                    AS taxable_value_paise,

                SUM(cgst_paise)
                    AS cgst_paise,

                SUM(sgst_paise)
                    AS sgst_paise,

                SUM(igst_paise)
                    AS igst_paise,

                SUM(total_tax_paise)
                    AS total_tax_paise,

                SUM(grand_total_paise)
                    AS invoice_value_paise

            FROM invoice_headers

            WHERE invoice_date BETWEEN ? AND ?

              AND status = 'issued'

            GROUP BY
                tax_period,
                supply_type

            ORDER BY
                tax_period,
                supply_type
            """,
            (
                start_date,
                end_date,
            ),
        ).fetchall()

        result = []

        for row in rows:

            data = dict(row)

            monetary_fields = [
                "taxable_value_paise",
                "cgst_paise",
                "sgst_paise",
                "igst_paise",
                "total_tax_paise",
                "invoice_value_paise",
            ]

            for field in monetary_fields:

                data[
                    field.replace("_paise", "_rupees")
                ] = data[field] / 100

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 11. RECEIVABLES REPORT
# ============================================================

def get_receivables_report():

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                ih.invoice_id,

                ih.invoice_number,

                ih.invoice_date,

                ih.customer_id,

                c.customer_name,

                ih.grand_total_paise,

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

                    SUM(allocated_amount_paise)
                        AS received_paise

                FROM payment_allocations

                GROUP BY invoice_id

            ) payments

                ON ih.invoice_id = payments.invoice_id

            WHERE ih.status = 'issued'

            ORDER BY
                ih.invoice_date,
                ih.invoice_id
            """
        ).fetchall()

        result = []

        today = date.today()

        for row in rows:

            data = dict(row)

            total = int(
                data["grand_total_paise"]
            )

            received = int(
                data["received_paise"]
            )

            outstanding = total - received

            invoice_date = date.fromisoformat(
                data["invoice_date"]
            )

            due_date = (
                invoice_date
                + pd.Timedelta(days=30)
            ).date()

            overdue_days = max(
                0,
                (today - due_date).days,
            )

            if outstanding == 0:

                payment_status = "Paid"

            elif received > 0:

                payment_status = "Partially Paid"

            else:

                payment_status = "Unpaid"

            data["outstanding_paise"] = outstanding

            data["invoice_total_rupees"] = total / 100

            data["received_rupees"] = received / 100

            data["outstanding_rupees"] = outstanding / 100

            data["due_date"] = due_date.isoformat()

            data["overdue_days"] = (
                overdue_days
                if outstanding > 0
                else 0
            )

            data["payment_status"] = payment_status

            result.append(data)

        return result

    finally:

        conn.close()


# ============================================================
# 12. PROFITABILITY REPORT
# ============================================================

def get_profitability_report():

    return get_product_profitability()


# ============================================================
# 13. USER ACTIVITY AUDIT REPORT
# ============================================================

def get_user_activity_report(
    start_date,
    end_date,
):

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    conn = get_connection()

    try:

        rows = conn.execute(
            """
            SELECT

                a.user_id,

                u.username,

                u.full_name,

                a.action,

                a.entity_type,

                a.entity_id,

                a.details,

                a.created_at

            FROM audit_logs a

            LEFT JOIN users u

                ON a.user_id = u.user_id

            WHERE date(a.created_at) BETWEEN ? AND ?

            ORDER BY a.created_at DESC
            """,
            (
                start_date,
                end_date,
            ),
        ).fetchall()

        return rows_to_dicts(rows)

    finally:

        conn.close()


# ============================================================
# 14. REPORT DASHBOARD SUMMARY
# ============================================================

def get_report_dashboard_summary(
    start_date,
    end_date,
):

    sales = get_sales_report(
        start_date,
        end_date,
    )

    purchases = get_purchase_report(
        start_date,
        end_date,
    )

    production = get_production_performance_report(
        start_date,
        end_date,
    )

    sales_value = sum(
        row["grand_total_paise"]
        for row in sales
    )

    taxable_sales = sum(
        row["taxable_value_paise"]
        for row in sales
    )

    purchase_value = sum(
        row["total_amount_paise"]
        for row in purchases
    )

    produced_packets = sum(
        row["actual_good_packets"]
        for row in production
    )

    return {

        "invoice_count": len(sales),

        "sales_value_paise": sales_value,

        "taxable_sales_paise": taxable_sales,

        "purchase_count": len(purchases),

        "purchase_value_paise": purchase_value,

        "production_run_count": len(production),

        "produced_packets": produced_packets,

    }


# ============================================================
# 15. GENERATE EXCEL REPORT
# ============================================================

def generate_excel_report(
    start_date,
    end_date,
):

    """
    Generates an Excel workbook containing the main
    FactoryFlow management and audit reports.

    Required packages:
    pandas
    openpyxl
    """

    start_date, end_date = validate_date_range(
        start_date,
        end_date,
    )

    reports = {

        "Sales": get_sales_report(
            start_date,
            end_date,
        ),

        "Daily Sales": get_daily_sales_summary(
            start_date,
            end_date,
        ),

        "Monthly Sales": get_monthly_sales_summary(
            start_date,
            end_date,
        ),

        "Purchases": get_purchase_report(
            start_date,
            end_date,
        ),

        "Inventory Position": get_inventory_position_report(),

        "Stock Movements": get_inventory_movement_report(
            start_date,
            end_date,
        ),

        "Production": get_production_performance_report(
            start_date,
            end_date,
        ),

        "Material Variance": get_material_variance_report(
            start_date,
            end_date,
        ),

        "GST Summary": get_gst_summary_report(
            start_date,
            end_date,
        ),

        "Receivables": get_receivables_report(),

        "Profitability": get_profitability_report(),

        "Audit Log": get_user_activity_report(
            start_date,
            end_date,
        ),

    }

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:

        for sheet_name, records in reports.items():

            dataframe = pd.DataFrame(records)

            dataframe.to_excel(
                writer,
                sheet_name=sheet_name[:31],
                index=False,
            )

            worksheet = writer.sheets[
                sheet_name[:31]
            ]

            worksheet.freeze_panes = "A2"

            worksheet.auto_filter.ref = (
                worksheet.dimensions
            )

            for column_cells in worksheet.columns:

                max_length = 0

                column_letter = (
                    column_cells[0].column_letter
                )

                for cell in column_cells:

                    if cell.value is not None:

                        max_length = max(
                            max_length,
                            len(str(cell.value)),
                        )

                worksheet.column_dimensions[
                    column_letter
                ].width = min(
                    max_length + 3,
                    35,
                )

    output.seek(0)

    return output.getvalue()