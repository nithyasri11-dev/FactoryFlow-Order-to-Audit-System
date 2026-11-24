from pathlib import Path
import ast
import importlib
import sys

import pytest


# ============================================================
# 1. PROJECT PATH CONFIGURATION
# ============================================================

# Locate the main project directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Add the project root to Python's import path.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================
# 2. REQUIRED PROJECT FILES
# ============================================================

REQUIRED_FILES = [
    "app.py",
    "database.py",
    "requirements.txt",

    "modules/__init__.py",
    "modules/authentication.py",
    "modules/masters.py",
    "modules/bom.py",
    "modules/inventory.py",
    "modules/production.py",
    "modules/sales.py",
    "modules/invoicing.py",
    "modules/dispatch.py",
    "modules/payments.py",
    "modules/costing.py",
    "modules/reports.py",

    "tests/test_module_integrity.py",
]


def test_required_files_exist():

    for file_name in REQUIRED_FILES:

        file_path = PROJECT_ROOT / file_name

        assert file_path.exists(), (
            f"Missing required file: {file_name}"
        )


# ============================================================
# 3. PYTHON SYNTAX VALIDATION
# ============================================================

def test_python_files_have_valid_syntax():

    python_files = list(PROJECT_ROOT.rglob("*.py"))

    excluded_directories = {
        ".venv",
        "venv",
        "__pycache__",
    }

    for file_path in python_files:

        if any(
            part in excluded_directories
            for part in file_path.parts
        ):
            continue

        source_code = file_path.read_text(
            encoding="utf-8"
        )

        try:

            ast.parse(source_code)

        except SyntaxError as error:

            pytest.fail(
                f"Syntax error in {file_path}: {error}"
            )


# ============================================================
# 4. REQUIRED MODULE FUNCTIONS
# ============================================================

MODULE_FUNCTIONS = {

    "modules.authentication": [
        "count_users",
        "create_user",
        "authenticate_user",
        "get_all_users",
    ],

    "modules.masters": [
        "create_customer",
        "create_supplier",
        "create_inventory_item",
        "create_finished_product",
        "get_customers",
        "get_suppliers",
        "get_inventory_items",
        "get_products",
    ],

    "modules.bom": [
        "create_bom",
        "get_boms",
        "get_bom_details",
    ],

    "modules.inventory": [
        "record_opening_stock",
        "get_opening_stock_item_ids",
        "get_stock_summary",
        "create_purchase",
        "get_purchase_register",
        "get_stock_ledger",
    ],

    "modules.production": [
        "get_active_boms",
        "get_bom_recipe",
        "post_production_run",
        "get_production_runs",
        "get_production_run_details",
    ],

    "modules.sales": [
        "initialize_sales_tables",
        "create_sales_order",
        "get_sales_orders",
        "get_sales_order_details",
        "get_product_stock_availability",
        "review_sales_order",
    ],

    "modules.invoicing": [
        "initialize_invoice_tables",
        "get_orders_pending_invoice",
        "create_invoice_from_order",
        "get_invoice_register",
        "get_invoice_details",
    ],

    "modules.dispatch": [
        "initialize_dispatch_tables",
        "get_orders_ready_for_dispatch",
        "get_order_dispatch_details",
        "create_dispatch",
        "get_dispatch_register",
        "get_dispatch_details",
        "mark_dispatch_delivered",
    ],

    "modules.payments": [
        "initialize_payment_tables",
        "get_open_invoices",
        "record_customer_payment",
        "get_payment_register",
        "get_payment_details",
        "get_customer_outstanding_summary",
        "get_overdue_invoices",
    ],

    "modules.costing": [
        "initialize_costing_tables",
        "set_inventory_cost_rate",
        "get_inventory_cost_rates",
        "get_uncosted_production_runs",
        "get_production_run_materials",
        "create_production_costing",
        "get_production_cost_register",
        "get_production_cost_details",
        "get_product_profitability",
    ],

    "modules.reports": [
        "get_sales_report",
        "get_daily_sales_summary",
        "get_monthly_sales_summary",
        "get_purchase_report",
        "get_inventory_position_report",
        "get_inventory_movement_report",
        "get_production_performance_report",
        "get_material_variance_report",
        "get_gst_summary_report",
        "get_receivables_report",
        "get_profitability_report",
        "get_user_activity_report",
        "get_report_dashboard_summary",
        "generate_excel_report",
    ],
}


# ============================================================
# 5. MODULE IMPORT VALIDATION
# ============================================================

@pytest.mark.parametrize(
    "module_name",
    MODULE_FUNCTIONS.keys(),
)
def test_module_imports(module_name):

    module = importlib.import_module(module_name)

    assert module is not None


# ============================================================
# 6. REQUIRED FUNCTION VALIDATION
# ============================================================

@pytest.mark.parametrize(
    "module_name,symbol_name",
    [
        (module_name, symbol_name)
        for module_name, symbols in MODULE_FUNCTIONS.items()
        for symbol_name in symbols
    ],
)
def test_required_functions_exist(module_name, symbol_name):

    module = importlib.import_module(module_name)

    assert hasattr(module, symbol_name), (
        f"{module_name} is missing {symbol_name}"
    )

    assert callable(getattr(module, symbol_name)), (
        f"{module_name}.{symbol_name} must be callable"
    )


# ============================================================
# 7. DATABASE INITIALIZATION VALIDATION
# ============================================================

def test_database_initializer_exists():

    database = importlib.import_module("database")

    assert hasattr(
        database,
        "initialize_database"
    ), "database.py is missing initialize_database"

    assert callable(
        database.initialize_database
    ), "initialize_database must be callable"


# ============================================================
# 8. USER ROLE VALIDATION
# ============================================================

def test_required_user_roles_exist():

    authentication = importlib.import_module(
        "modules.authentication"
    )

    assert hasattr(
        authentication,
        "ROLES"
    ), "ROLES is missing from authentication.py"

    roles = authentication.ROLES

    expected_roles = [
        "admin",
        "salesman",
        "production",
        "owner",
        "auditor",
    ]

    role_text = str(roles).lower()

    for role in expected_roles:

        assert role in role_text, (
            f"Missing user role: {role}"
        )


# ============================================================
# 9. REQUIREMENTS VALIDATION
# ============================================================

def test_required_packages_are_declared():

    requirements_path = PROJECT_ROOT / "requirements.txt"

    assert requirements_path.exists(), (
        "requirements.txt is missing"
    )

    requirements = requirements_path.read_text(
        encoding="utf-8"
    ).lower()

    required_packages = [
        "streamlit",
        "pandas",
        "plotly",
        "reportlab",
        "argon2-cffi",
        "openpyxl",
        "pytest",
    ]

    for package in required_packages:

        assert package in requirements, (
            f"Missing package in requirements.txt: {package}"
        )


# ============================================================
# 10. APP ENTRY POINT VALIDATION
# ============================================================

def test_app_file_exists():

    app_path = PROJECT_ROOT / "app.py"

    assert app_path.exists()

    source_code = app_path.read_text(
        encoding="utf-8"
    )

    assert "def main" in source_code, (
        "app.py must contain a main() function"
    )

    assert 'if __name__ == "__main__"' in source_code, (
        "app.py must contain the application entry point"
    )