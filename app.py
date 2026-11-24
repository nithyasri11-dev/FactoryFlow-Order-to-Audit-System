import streamlit as st
import pandas as pd
from datetime import date, timedelta

from database import initialize_database, get_connection

# ============================================================
# 1. MODULE IMPORTS
# ============================================================

from modules.authentication import (
    count_users,
    create_user,
    authenticate_user,
    get_all_users,
    ROLES,
)

from modules.masters import (
    create_customer,
    create_supplier,
    create_inventory_item,
    create_finished_product,
    get_customers,
    get_suppliers,
    get_inventory_items,
    get_products,
)

from modules.bom import (
    create_bom,
    get_boms,
    get_bom_details,
)

from modules.inventory import (
    record_opening_stock,
    get_opening_stock_item_ids,
    get_stock_summary,
    create_purchase,
    get_purchase_register,
    get_stock_ledger,
)

from modules.production import (
    get_active_boms,
    get_bom_recipe,
    post_production_run,
    get_production_runs,
    get_production_run_details,
)

from modules.sales import (
    initialize_sales_tables,
    create_sales_order,
    get_sales_orders,
    get_product_stock_availability,
    review_sales_order,
)

from modules.invoicing import (
    initialize_invoice_tables,
    get_orders_pending_invoice,
    create_invoice_from_order,
    get_invoice_register,
    get_invoice_details,
    SUPPLIER_STATE,
)

from modules.dispatch import (
    initialize_dispatch_tables,
    get_orders_ready_for_dispatch,
    get_order_dispatch_details,
    create_dispatch,
    get_dispatch_register,
    get_dispatch_details,
    mark_dispatch_delivered,
)

from modules.payments import (
    initialize_payment_tables,
    get_open_invoices,
    record_customer_payment,
    get_payment_register,
    get_payment_details,
    get_customer_outstanding_summary,
    get_overdue_invoices,
)

from modules.costing import (
    initialize_costing_tables,
    set_inventory_cost_rate,
    get_inventory_cost_rates,
    get_uncosted_production_runs,
    get_production_run_materials,
    create_production_costing,
    get_production_cost_register,
    get_production_cost_details,
    get_product_profitability,
)

from modules.reports import (
    get_sales_report,
    get_daily_sales_summary,
    get_monthly_sales_summary,
    get_purchase_report,
    get_inventory_position_report,
    get_inventory_movement_report,
    get_production_performance_report,
    get_material_variance_report,
    get_gst_summary_report,
    get_receivables_report,
    get_profitability_report,
    get_user_activity_report,
    get_report_dashboard_summary,
    generate_excel_report,
)


# ============================================================
# 2. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="FactoryFlow | Order-to-Audit Management",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 3. DATABASE INITIALIZATION
# ============================================================

initialize_database()
initialize_sales_tables()
initialize_invoice_tables()
initialize_dispatch_tables()
initialize_payment_tables()
initialize_costing_tables()


# ============================================================
# 4. APPLICATION STYLING
# ============================================================

st.markdown(
    """
    <style>
        .app-title {
            font-size: 2.3rem;
            font-weight: 800;
            color: #0f766e;
            margin-bottom: 0;
        }

        .app-subtitle {
            color: #64748b;
            font-size: 1rem;
            margin-top: -0.25rem;
        }

        div[data-testid="stMetric"] {
            border: 1px solid rgba(128, 128, 128, 0.2);
            border-radius: 0.7rem;
            padding: 0.8rem;
        }

        .section-heading {
            font-weight: 700;
            color: #0f766e;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 5. COMMON HELPER FUNCTIONS
# ============================================================

def show_header():
    st.markdown(
        '<p class="app-title">🏭 FactoryFlow</p>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <p class="app-subtitle">
        Order-to-Audit Management System for Food Manufacturers
        </p>
        """,
        unsafe_allow_html=True,
    )

    st.divider()


def show_footer():
    st.divider()

    st.caption(
        "FactoryFlow | NIT Trichy CDI Internship Project | "
        "Educational prototype"
    )


def show_table(records, message="No records available."):
    if records is not None and len(records) > 0:
        st.dataframe(
            records,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(message)


def show_error(exc):
    st.error(str(exc))


def format_rupees(value):
    return f"₹{float(value):,.2f}"


def date_range_controls(key_prefix):
    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "Start date",
            value=date.today() - timedelta(days=30),
            key=f"{key_prefix}_start",
        )

    with col2:
        end_date = st.date_input(
            "End date",
            value=date.today(),
            key=f"{key_prefix}_end",
        )

    return start_date, end_date


def check_date_range(start_date, end_date):
    if start_date > end_date:
        st.error("Start date cannot be later than end date.")
        return False

    return True


def option_dictionary(records, label_function, id_field):
    return {
        label_function(record): record[id_field]
        for record in records
    }


def get_sales_order_details(order_id):
    """
    Retrieve sales order details.

    item_code is stored in inventory_items, not products.
    This query joins the correct tables.
    """

    conn = get_connection()

    try:
        order_row = conn.execute(
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

        if not order_row:
            return None

        item_rows = conn.execute(
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

        order = dict(order_row)

        order["subtotal_rupees"] = (
            int(order.get("subtotal_paise", 0)) / 100
        )

        order["total_amount_rupees"] = (
            int(order.get("total_amount_paise", 0)) / 100
        )

        items = []

        for row in item_rows:
            item = dict(row)

            item["unit_rate_rupees"] = (
                int(item["unit_rate_paise"]) / 100
            )

            item["line_total_rupees"] = (
                int(item["line_total_paise"]) / 100
            )

            items.append(item)

        return {
            "order": order,
            "items": items,
        }

    finally:
        conn.close()


# ============================================================
# 6. INITIAL ADMINISTRATOR SETUP
# ============================================================

def render_initial_admin_setup():

    st.header("🔐 Initial Administrator Setup")

    st.info(
        "Create the first administrator account to start using "
        "FactoryFlow."
    )

    with st.form("initial_admin_form"):

        full_name = st.text_input("Administrator full name")
        username = st.text_input("Username")

        password = st.text_input(
            "Create password",
            type="password",
        )

        confirm_password = st.text_input(
            "Confirm password",
            type="password",
        )

        submitted = st.form_submit_button(
            "Create administrator account",
            use_container_width=True,
        )

    if submitted:

        if not full_name.strip() or not username.strip():
            st.error("Enter the administrator name and username.")

        elif password != confirm_password:
            st.error("The passwords do not match.")

        else:
            try:
                create_user(
                    username,
                    full_name,
                    password,
                    "admin",
                )

                st.success(
                    "Administrator account created successfully."
                )

                st.rerun()

            except Exception as exc:
                show_error(exc)


# ============================================================
# 7. LOGIN
# ============================================================

def render_login():

    left, right = st.columns([1.2, 1])

    with left:

        st.subheader("Welcome to FactoryFlow")

        st.write(
            """
            FactoryFlow is a centralized order-to-audit management
            application designed for food manufacturing businesses.
            """
        )

        st.markdown(
            """
            **Application Modules**

            - Customer and supplier management
            - Inventory and purchasing
            - Bill of Materials management
            - Production management
            - Sales order management
            - GST invoicing
            - Dispatch and delivery
            - Payment tracking
            - Product costing
            - Audit reports and analytics
            """
        )

    with right:

        st.subheader("🔑 User Login")

        with st.form("login_form"):

            username = st.text_input("Username")

            password = st.text_input(
                "Password",
                type="password",
            )

            submitted = st.form_submit_button(
                "Login",
                use_container_width=True,
            )

        if submitted:

            try:
                user = authenticate_user(username, password)

                if user:
                    st.session_state["current_user"] = user
                    st.rerun()

                else:
                    st.error(
                        "Invalid username or password, "
                        "or the account is inactive."
                    )

            except Exception as exc:
                show_error(exc)


# ============================================================
# 8. DASHBOARD
# ============================================================

def render_dashboard(user):

    st.header("📊 FactoryFlow Dashboard")

    st.write(f"Welcome, **{user['full_name']}**.")

    st.success(
        f"Signed in with the {user['role'].title()} role."
    )

    customers = get_customers()
    suppliers = get_suppliers()
    inventory_items = get_inventory_items()
    products = get_products()
    orders = get_sales_orders()
    production_runs = get_production_runs()

    col1, col2, col3 = st.columns(3)

    col1.metric("Customers", len(customers))
    col2.metric("Suppliers", len(suppliers))
    col3.metric("Inventory Items", len(inventory_items))

    col4, col5, col6 = st.columns(3)

    col4.metric("Finished Products", len(products))
    col5.metric("Sales Orders", len(orders))
    col6.metric("Production Runs", len(production_runs))

    st.divider()

    st.subheader("Business Workflow")

    workflow = [
        "1. Register customers, suppliers and products",
        "2. Define Bill of Materials",
        "3. Record opening inventory and purchases",
        "4. Complete production runs",
        "5. Create and approve sales orders",
        "6. Generate GST invoices",
        "7. Dispatch finished goods",
        "8. Record customer payments",
        "9. Review product costing and profitability",
        "10. Generate audit and management reports",
    ]

    for step in workflow:
        st.write(step)


# ============================================================
# 9. USER MANAGEMENT
# ============================================================

def render_user_management(user):

    st.header("👥 User Management")

    if user["role"] != "admin":
        st.error("Only administrators can manage user accounts.")
        return

    create_tab, view_tab = st.tabs(
        ["Create User", "Registered Users"]
    )

    with create_tab:

        with st.form("create_user_form"):

            full_name = st.text_input("Full name")
            username = st.text_input("Username")

            role = st.selectbox(
                "Role",
                ROLES,
            )

            password = st.text_input(
                "Password",
                type="password",
            )

            confirm_password = st.text_input(
                "Confirm password",
                type="password",
            )

            submitted = st.form_submit_button(
                "Create User",
                use_container_width=True,
            )

        if submitted:

            if not full_name.strip() or not username.strip():
                st.error("Name and username are required.")

            elif password != confirm_password:
                st.error("Passwords do not match.")

            else:
                try:
                    create_user(
                        username,
                        full_name,
                        password,
                        role,
                    )

                    st.success("User created successfully.")
                    st.rerun()

                except Exception as exc:
                    show_error(exc)

    with view_tab:

        show_table(
            get_all_users(),
            "No users registered.",
        )


# ============================================================
# 10. MASTER DATA MANAGEMENT
# ============================================================

def render_master_data(user):

    st.header("📦 Master Data Management")

    can_edit = user["role"] == "admin"

    customer_tab, supplier_tab, inventory_tab, product_tab = st.tabs(
        [
            "Customers",
            "Suppliers",
            "Inventory Items",
            "Finished Products",
        ]
    )

    # ---------------- CUSTOMERS ----------------

    with customer_tab:

        st.subheader("Customer Registration")

        if can_edit:

            with st.form("customer_form"):

                customer_name = st.text_input("Customer name")

                customer_type = st.selectbox(
                    "Customer type",
                    ["Retailer", "Distributor"],
                )

                state = st.text_input(
                    "State",
                    value="Tamil Nadu",
                )

                gstin = st.text_input("GSTIN")

                phone = st.text_input("Phone number")

                submitted = st.form_submit_button("Add Customer")

            if submitted:
                try:
                    create_customer(
                        customer_name,
                        customer_type,
                        state,
                        gstin,
                        phone,
                    )

                    st.success("Customer added successfully.")
                    st.rerun()

                except Exception as exc:
                    show_error(exc)

        show_table(
            get_customers(),
            "No customers registered.",
        )

    # ---------------- SUPPLIERS ----------------

    with supplier_tab:

        st.subheader("Supplier Registration")

        if can_edit:

            with st.form("supplier_form"):

                supplier_name = st.text_input("Supplier name")

                state = st.text_input(
                    "Supplier state",
                    value="Tamil Nadu",
                )

                gstin = st.text_input("Supplier GSTIN")

                phone = st.text_input("Supplier phone")

                submitted = st.form_submit_button("Add Supplier")

            if submitted:
                try:
                    create_supplier(
                        supplier_name,
                        state,
                        gstin,
                        phone,
                    )

                    st.success("Supplier added successfully.")
                    st.rerun()

                except Exception as exc:
                    show_error(exc)

        show_table(
            get_suppliers(),
            "No suppliers registered.",
        )

    # ---------------- INVENTORY ITEMS ----------------

    with inventory_tab:

        st.subheader("Inventory Item Registration")

        if can_edit:

            with st.form("inventory_form"):

                item_code = st.text_input("Item code")
                item_name = st.text_input("Item name")

                category = st.selectbox(
                    "Category",
                    [
                        "raw_material",
                        "packaging_material",
                    ],
                )

                base_unit = st.selectbox(
                    "Base unit",
                    [
                        "kg",
                        "g",
                        "litre",
                        "piece",
                    ],
                )

                reorder_level = st.number_input(
                    "Reorder level",
                    min_value=0.0,
                    value=0.0,
                    step=1.0,
                    format="%.3f",
                )

                submitted = st.form_submit_button("Add Inventory Item")

            if submitted:
                try:
                    create_inventory_item(
                        item_code,
                        item_name,
                        category,
                        base_unit,
                        reorder_level,
                    )

                    st.success("Inventory item added.")
                    st.rerun()

                except Exception as exc:
                    show_error(exc)

        show_table(
            get_inventory_items(),
            "No inventory items registered.",
        )

    # ---------------- FINISHED PRODUCTS ----------------

    with product_tab:

        st.subheader("Finished Product Registration")

        if can_edit:

            with st.form("product_form"):

                product_name = st.text_input("Product name")
                item_code = st.text_input("Finished goods item code")

                pack_size_g = st.number_input(
                    "Pack size in grams",
                    min_value=1,
                    value=200,
                    step=50,
                )

                selling_price = st.number_input(
                    "Selling price before GST (₹)",
                    min_value=0.01,
                    value=50.0,
                    step=1.0,
                )

                gst_percent = st.selectbox(
                    "GST rate",
                    [5, 12, 18],
                )

                hsn_code = st.text_input("HSN code")

                submitted = st.form_submit_button("Add Product")

            if submitted:
                try:
                    create_finished_product(
                        product_name,
                        item_code,
                        pack_size_g,
                        selling_price,
                        gst_percent,
                        hsn_code,
                    )

                    st.success("Finished product added.")
                    st.rerun()

                except Exception as exc:
                    show_error(exc)

        show_table(
            get_products(),
            "No finished products registered.",
        )


# ============================================================
# 11. BILL OF MATERIALS MANAGEMENT
# ============================================================

def render_bom_management(user):

    st.header("📋 Bill of Materials Management")

    can_edit = user["role"] == "admin"

    products = get_products()

    inventory_items = [
        item
        for item in get_inventory_items()
        if item["category"] in (
            "raw_material",
            "packaging_material",
        )
    ]

    if can_edit:

        st.subheader("Create BOM")

        if not products:
            st.warning("Register finished products first.")

        elif not inventory_items:
            st.warning("Register inventory items first.")

        else:

            product_options = {
                (
                    f"{p['product_name']} "
                    f"({p['pack_size_g']} g)"
                ): p["product_id"]
                for p in products
            }

            item_options = {
                (
                    f"{item['item_name']} "
                    f"({item['base_unit']})"
                ): item["item_id"]
                for item in inventory_items
            }

            component_count = st.number_input(
                "Number of BOM components",
                min_value=1,
                max_value=15,
                value=min(3, len(item_options)),
                key="bom_component_count",
            )

            with st.form("bom_form"):

                selected_product = st.selectbox(
                    "Finished product",
                    list(product_options.keys()),
                )

                expected_yield = st.number_input(
                    "Expected packets per batch",
                    min_value=1,
                    value=200,
                )

                components = []

                for index in range(int(component_count)):

                    col1, col2 = st.columns(2)

                    with col1:

                        selected_item = st.selectbox(
                            f"Component {index + 1}",
                            list(item_options.keys()),
                            key=f"bom_item_{index}",
                        )

                    with col2:

                        quantity = st.number_input(
                            "Quantity per batch",
                            min_value=0.001,
                            value=1.0,
                            step=0.1,
                            format="%.3f",
                            key=f"bom_qty_{index}",
                        )

                    components.append(
                        (
                            item_options[selected_item],
                            quantity,
                        )
                    )

                submitted = st.form_submit_button("Save BOM")

            if submitted:
                try:
                    bom_id = create_bom(
                        product_options[selected_product],
                        expected_yield,
                        components,
                    )

                    st.success(f"BOM created. ID: {bom_id}")
                    st.rerun()

                except Exception as exc:
                    show_error(exc)

    st.divider()

    st.subheader("Registered BOMs")

    boms = get_boms()

    if not boms:
        st.info("No BOMs available.")
        return

    bom_rows = [
        {
            "BOM ID": b["bom_id"],
            "Product": b["product_name"],
            "Version": b["version"],
            "Expected Output": b["expected_yield_packets"],
            "Active": b["active"],
        }
        for b in boms
    ]

    show_table(bom_rows)

    bom_options = {
        (
            f"BOM {b['bom_id']} - "
            f"{b['product_name']} - "
            f"Version {b['version']}"
        ): b["bom_id"]
        for b in boms
    }

    selected_bom = st.selectbox(
        "View BOM recipe",
        list(bom_options.keys()),
    )

    details = get_bom_details(bom_options[selected_bom])

    if details:

        st.subheader("BOM Recipe")

        st.write(
            f"Product: {details['bom']['product_name']}"
        )

        show_table(details["components"])


# ============================================================
# 12. INVENTORY AND PURCHASE MANAGEMENT
# ============================================================

def render_inventory_purchases(user):

    st.header("📦 Inventory and Purchase Management")

    can_edit = user["role"] == "admin"

    stock_tab, opening_tab, purchase_tab, ledger_tab, register_tab = st.tabs(
        [
            "Stock Summary",
            "Opening Stock",
            "Record Purchase",
            "Stock Ledger",
            "Purchase Register",
        ]
    )

    items = get_inventory_items()
    suppliers = get_suppliers()

    # ---------------- STOCK SUMMARY ----------------

    with stock_tab:

        st.subheader("Current Stock Position")

        stock = get_stock_summary()

        show_table(
            stock,
            "No inventory stock records available.",
        )

    # ---------------- OPENING STOCK ----------------

    with opening_tab:

        st.subheader("Record Opening Stock")

        if not can_edit:
            st.info("Only administrators can record opening stock.")

        elif not items:
            st.warning("Register inventory items first.")

        else:

            already_recorded = get_opening_stock_item_ids()

            pending_items = [
                item
                for item in items
                if item["item_id"] not in already_recorded
            ]

            if not pending_items:

                st.success(
                    "Opening stock is already recorded for all items."
                )

            else:

                with st.form("opening_stock_form"):

                    entries = []

                    for item in pending_items:

                        quantity = st.number_input(
                            (
                                f"{item['item_name']} "
                                f"({item['base_unit']})"
                            ),
                            min_value=0.0,
                            value=0.0,
                            step=1.0,
                            format="%.3f",
                            key=f"opening_{item['item_id']}",
                        )

                        entries.append(
                            (
                                item["item_id"],
                                quantity,
                            )
                        )

                    submitted = st.form_submit_button(
                        "Post Opening Stock"
                    )

                if submitted:
                    try:
                        record_opening_stock(
                            entries,
                            user["user_id"],
                        )

                        st.success("Opening stock posted.")
                        st.rerun()

                    except Exception as exc:
                        show_error(exc)

    # ---------------- PURCHASE ENTRY ----------------

    with purchase_tab:

        st.subheader("Record New Purchase")

        if not can_edit:
            st.info("Only administrators can record purchases.")

        elif not suppliers:
            st.warning("Register suppliers first.")

        elif not items:
            st.warning("Register inventory items first.")

        else:

            purchase_items = [
                item
                for item in items
                if item["category"] in (
                    "raw_material",
                    "packaging_material",
                )
            ]

            if not purchase_items:
                st.warning(
                    "Register raw materials or packaging materials first."
                )
            else:

                supplier_options = {
                    s["supplier_name"]: s["supplier_id"]
                    for s in suppliers
                }

                item_options = {
                    i["item_name"]: i["item_id"]
                    for i in purchase_items
                }

                with st.form("purchase_form"):

                    supplier_name = st.selectbox(
                        "Supplier",
                        list(supplier_options.keys()),
                    )

                    invoice_reference = st.text_input(
                        "Supplier invoice reference"
                    )

                    purchase_date = st.date_input(
                        "Purchase date",
                        value=date.today(),
                    )

                    line_count = st.number_input(
                        "Number of purchase items",
                        min_value=1,
                        max_value=10,
                        value=1,
                    )

                    purchase_lines = []

                    for index in range(int(line_count)):

                        st.markdown(
                            f"**Purchase item {index + 1}**"
                        )

                        col1, col2, col3 = st.columns(3)

                        with col1:

                            item_name = st.selectbox(
                                "Inventory item",
                                list(item_options.keys()),
                                key=f"purchase_item_{index}",
                            )

                        with col2:

                            quantity = st.number_input(
                                "Quantity",
                                min_value=0.001,
                                value=1.0,
                                step=1.0,
                                key=f"purchase_quantity_{index}",
                            )

                        with col3:

                            unit_rate = st.number_input(
                                "Rate per unit (₹)",
                                min_value=0.01,
                                value=1.0,
                                step=1.0,
                                key=f"purchase_rate_{index}",
                            )

                        purchase_lines.append(
                            (
                                item_options[item_name],
                                quantity,
                                unit_rate,
                            )
                        )

                    submitted = st.form_submit_button(
                        "Post Purchase"
                    )

                if submitted:
                    try:
                        result = create_purchase(
                            supplier_options[supplier_name],
                            invoice_reference,
                            purchase_date.isoformat(),
                            purchase_lines,
                            user["user_id"],
                        )

                        st.success(
                            f"Purchase #{result['purchase_id']} posted."
                        )

                        st.metric(
                            "Purchase Total",
                            format_rupees(
                                result["total_paise"] / 100
                            ),
                        )

                        st.rerun()

                    except Exception as exc:
                        show_error(exc)

    # ---------------- STOCK LEDGER ----------------

    with ledger_tab:

        st.subheader("Stock Movement Ledger")

        item_options = {
            "All Items": None,
        }

        for item in items:

            item_options[
                f"{item['item_name']} ({item['base_unit']})"
            ] = item["item_id"]

        selected_item = st.selectbox(
            "Filter inventory item",
            list(item_options.keys()),
        )

        ledger = get_stock_ledger(
            item_options[selected_item]
        )

        show_table(
            ledger,
            "No stock movements found.",
        )

    # ---------------- PURCHASE REGISTER ----------------

    with register_tab:

        st.subheader("Purchase Register")

        show_table(
            get_purchase_register(),
            "No purchases recorded.",
        )


# ============================================================
# 13. PRODUCTION MANAGEMENT
# ============================================================

def render_production_management(user):

    st.header("🏭 Production Management")

    can_edit = user["role"] in (
        "admin",
        "production",
    )

    new_tab, history_tab = st.tabs(
        [
            "New Production Run",
            "Production History",
        ]
    )

    # ---------------- NEW PRODUCTION RUN ----------------

    with new_tab:

        if not can_edit:

            st.info(
                "You have read-only access to production management."
            )

        else:

            boms = get_active_boms()

            if not boms:

                st.warning("Create an active BOM first.")

            else:

                bom_options = {
                    (
                        f"{b['product_name']} "
                        f"- Version {b['version']}"
                    ): b["bom_id"]
                    for b in boms
                }

                selected_bom = st.selectbox(
                    "Select BOM",
                    list(bom_options.keys()),
                )

                selected_bom_id = bom_options[selected_bom]

                recipe = get_bom_recipe(selected_bom_id)

                if recipe:

                    bom = recipe["bom"]

                    st.metric(
                        "Expected Output per Batch",
                        bom["expected_yield_packets"],
                    )

                    batch_count = st.number_input(
                        "Number of batches",
                        min_value=1,
                        max_value=100,
                        value=1,
                    )

                    expected_output = (
                        int(bom["expected_yield_packets"])
                        * int(batch_count)
                    )

                    st.info(
                        f"Expected total output: {expected_output} packets"
                    )

                    planned_rows = []

                    for item in recipe["components"]:

                        planned_quantity = (
                            item["quantity_per_batch_milli"] / 1000
                        ) * batch_count

                        planned_rows.append(
                            {
                                "Material": item["item_name"],
                                "Planned Quantity": planned_quantity,
                                "Unit": item["base_unit"],
                            }
                        )

                    show_table(planned_rows)

                    with st.form("production_form"):

                        actual_consumptions = {}

                        for item in recipe["components"]:

                            item_id = item.get(
                                "inventory_item_id",
                                item.get("item_id"),
                            )

                            planned_quantity = (
                                item["quantity_per_batch_milli"] / 1000
                            ) * batch_count

                            actual_quantity = st.number_input(
                                (
                                    f"Actual {item['item_name']} "
                                    f"({item['base_unit']})"
                                ),
                                min_value=0.0,
                                value=float(planned_quantity),
                                step=0.1,
                                format="%.3f",
                                key=f"actual_{item_id}",
                            )

                            actual_consumptions[item_id] = actual_quantity

                        st.markdown("### Production Output")

                        actual_good_packets = st.number_input(
                            "Good packets produced",
                            min_value=0,
                            value=int(expected_output),
                        )

                        damaged_pouches = st.number_input(
                            "Damaged pouches",
                            min_value=0,
                            value=0,
                        )

                        cartons_used = st.number_input(
                            "Cartons used",
                            min_value=0,
                            value=0,
                        )

                        submitted = st.form_submit_button(
                            "Complete Production Run"
                        )

                    if submitted:
                        try:
                            result = post_production_run(
                                selected_bom_id,
                                batch_count,
                                actual_consumptions,
                                actual_good_packets,
                                damaged_pouches,
                                cartons_used,
                                user["user_id"],
                                tolerance_percent=3,
                            )

                            st.success(
                                f"Production Run #{result['run_id']} completed."
                            )

                            col1, col2 = st.columns(2)

                            col1.metric(
                                "Actual Output",
                                result["actual_output"],
                            )

                            col2.metric(
                                "Yield Variance",
                                f"{result['yield_variance_percent']}%",
                            )

                            show_table(result["materials"])

                        except Exception as exc:
                            show_error(exc)

    # ---------------- PRODUCTION HISTORY ----------------

    with history_tab:

        st.subheader("Production Run Register")

        runs = get_production_runs()

        show_table(
            runs,
            "No production runs recorded.",
        )

        if runs:

            run_options = {
                (
                    f"Run #{r['run_id']} - "
                    f"{r['product_name']}"
                ): r["run_id"]
                for r in runs
            }

            selected_run = st.selectbox(
                "Select production run",
                list(run_options.keys()),
            )

            details = get_production_run_details(
                run_options[selected_run]
            )

            if details:

                st.subheader("Production Run Details")

                show_table(details["materials"])


# ============================================================
# 14. SALES ORDER MANAGEMENT
# ============================================================

def render_sales_orders(user):

    st.header("🛒 Sales Order Management")

    can_create = user["role"] in (
        "admin",
        "salesman",
    )

    can_review = user["role"] == "admin"

    create_tab, register_tab, review_tab = st.tabs(
        [
            "Create Sales Order",
            "Order Register",
            "Verify Orders",
        ]
    )

    # ---------------- CREATE ORDER ----------------

    with create_tab:

        customers = get_customers()
        products = get_products()

        if not can_create:

            st.info(
                "Only administrators and salesmen can create orders."
            )

        elif not customers or not products:

            st.warning(
                "Register customers and finished products first."
            )

        else:

            customer_options = {
                c["customer_name"]: c["customer_id"]
                for c in customers
            }

            product_options = {
                p["product_name"]: p["product_id"]
                for p in products
            }

            with st.form("sales_order_form"):

                customer_name = st.selectbox(
                    "Customer",
                    list(customer_options.keys()),
                )

                order_date = st.date_input(
                    "Order date",
                    value=date.today(),
                )

                required_date = st.date_input(
                    "Required delivery date",
                    value=date.today() + timedelta(days=7),
                )

                line_count = st.number_input(
                    "Number of products",
                    min_value=1,
                    max_value=10,
                    value=1,
                )

                order_lines = []

                for index in range(int(line_count)):

                    col1, col2, col3 = st.columns(3)

                    with col1:

                        product_name = st.selectbox(
                            "Product",
                            list(product_options.keys()),
                            key=f"sales_product_{index}",
                        )

                    with col2:

                        quantity = st.number_input(
                            "Quantity (packets)",
                            min_value=1,
                            value=10,
                            key=f"sales_qty_{index}",
                        )

                    with col3:

                        selling_price = st.number_input(
                            "Selling price per packet (₹)",
                            min_value=0.01,
                            value=50.0,
                            key=f"sales_price_{index}",
                        )

                    order_lines.append(
                        (
                            product_options[product_name],
                            quantity,
                            selling_price,
                        )
                    )

                notes = st.text_area("Order notes")

                submitted = st.form_submit_button(
                    "Submit Sales Order"
                )

            if submitted:
                try:
                    result = create_sales_order(
                        customer_options[customer_name],
                        order_date.isoformat(),
                        required_date.isoformat(),
                        order_lines,
                        user["user_id"],
                        notes,
                    )

                    st.success(
                        f"Sales Order #{result['order_id']} created."
                    )

                    st.metric(
                        "Order Total",
                        format_rupees(
                            result["total_amount_rupees"]
                        ),
                    )

                    st.rerun()

                except Exception as exc:
                    show_error(exc)

    # ---------------- ORDER REGISTER ----------------

    with register_tab:

        if user["role"] == "salesman":

            orders = get_sales_orders(
                created_by=user["user_id"]
            )

        else:

            orders = get_sales_orders()

        st.subheader("Sales Order Register")

        show_table(
            orders,
            "No sales orders available.",
        )

        if orders:

            order_options = {
                (
                    f"Order #{o['order_id']} - "
                    f"{o['customer_name']}"
                ): o["order_id"]
                for o in orders
            }

            selected_order = st.selectbox(
                "View order details",
                list(order_options.keys()),
            )

            details = get_sales_order_details(
                order_options[selected_order]
            )

            if details:

                st.subheader("Order Details")

                st.write(details["order"])

                show_table(details["items"])

    # ---------------- ORDER APPROVAL ----------------

    with review_tab:

        if not can_review:

            st.info(
                "Only administrators can approve or reject orders."
            )

        else:

            all_orders = get_sales_orders()

            pending_orders = [
                o
                for o in all_orders
                if o["status"] == "pending"
            ]

            if not pending_orders:

                st.success("No pending orders.")

            else:

                pending_options = {
                    (
                        f"Order #{o['order_id']} - "
                        f"{o['customer_name']}"
                    ): o["order_id"]
                    for o in pending_orders
                }

                selected = st.selectbox(
                    "Select pending order",
                    list(pending_options.keys()),
                )

                selected_order_id = pending_options[selected]

                details = get_sales_order_details(
                    selected_order_id
                )

                if details:

                    order = details["order"]

                    st.write(order)

                    stock_rows = []

                    for item in details["items"]:

                        stock = get_product_stock_availability(
                            item["product_id"]
                        )

                        stock_rows.append(
                            {
                                "Product": item["product_name"],
                                "Ordered": item["quantity_packets"],
                                "On Hand": stock["on_hand"],
                                "Reserved": stock["reserved"],
                                "Available": stock["available"],
                            }
                        )

                    show_table(stock_rows)

                    decision = st.radio(
                        "Decision",
                        [
                            "Approve",
                            "Reject",
                        ],
                        horizontal=True,
                    )

                    rejection_reason = ""

                    if decision == "Reject":

                        rejection_reason = st.text_area(
                            "Reason for rejection"
                        )

                    if st.button("Submit Order Decision"):

                        try:

                            if decision == "Approve":

                                review_sales_order(
                                    selected_order_id,
                                    user["user_id"],
                                    "approve",
                                )

                                st.success("Order approved.")

                            else:

                                review_sales_order(
                                    selected_order_id,
                                    user["user_id"],
                                    "reject",
                                    rejection_reason,
                                )

                                st.success("Order rejected.")

                            st.rerun()

                        except Exception as exc:
                            show_error(exc)


# ============================================================
# 15. GST INVOICING
# ============================================================

def render_invoicing(user):

    st.header("🧾 GST Invoicing and Billing")

    create_tab, register_tab = st.tabs(
        [
            "Create Invoice",
            "Invoice Register",
        ]
    )

    # ---------------- CREATE INVOICE ----------------

    with create_tab:

        if user["role"] != "admin":

            st.info(
                "Only administrators can generate GST invoices."
            )

        else:

            pending_orders = get_orders_pending_invoice()

            if not pending_orders:

                st.success(
                    "There are no approved orders pending invoicing."
                )

            else:

                order_options = {
                    (
                        f"Order #{o['order_id']} - "
                        f"{o['customer_name']}"
                    ): o["order_id"]
                    for o in pending_orders
                }

                selected_order = st.selectbox(
                    "Select approved sales order",
                    list(order_options.keys()),
                )

                selected_order_id = order_options[selected_order]

                st.info(
                    f"Supplier state used for GST calculation: "
                    f"{SUPPLIER_STATE}"
                )

                invoice_date = st.date_input(
                    "Invoice date",
                    value=date.today(),
                    key="invoice_date_input",
                )

                if st.button(
                    "Generate GST Invoice",
                    use_container_width=True,
                ):

                    try:

                        result = create_invoice_from_order(
                            selected_order_id,
                            invoice_date.isoformat(),
                            user["user_id"],
                        )

                        st.success(
                            "Invoice generated successfully."
                        )

                        if isinstance(result, dict):
                            st.write(result)

                        st.rerun()

                    except Exception as exc:
                        show_error(exc)

    # ---------------- INVOICE REGISTER ----------------

    with register_tab:

        invoices = get_invoice_register()

        show_table(
            invoices,
            "No invoices generated.",
        )

        if invoices:

            invoice_options = {
                (
                    f"{i['invoice_number']} - "
                    f"Invoice ID {i['invoice_id']}"
                ): i["invoice_id"]
                for i in invoices
            }

            selected_invoice = st.selectbox(
                "Select invoice",
                list(invoice_options.keys()),
            )

            details = get_invoice_details(
                invoice_options[selected_invoice]
            )

            if details:

                st.subheader("Invoice Details")

                if isinstance(details, dict):

                    for key, value in details.items():

                        if isinstance(value, list):

                            st.markdown(f"**{key.title()}**")
                            show_table(value)

                        elif isinstance(value, dict):

                            st.markdown(f"**{key.title()}**")
                            st.write(value)

                        else:

                            st.write(f"{key}: {value}")


# ============================================================
# 16. DISPATCH AND DELIVERY
# ============================================================

def render_dispatch_management(user):

    st.header("🚚 Dispatch and Delivery Management")

    create_tab, register_tab = st.tabs(
        ["Create Dispatch", "Dispatch Register"]
    )

    # ---------------- CREATE DISPATCH ----------------

    with create_tab:

        if user["role"] != "admin":

            st.info(
                "Only administrators can create dispatch records."
            )

        else:

            ready_orders = get_orders_ready_for_dispatch()

            if not ready_orders:

                st.success(
                    "No approved orders are currently ready for dispatch."
                )

            else:

                order_options = {
                    (
                        f"Order #{row['order_id']} - "
                        f"{row['customer_name']}"
                    ): row["order_id"]
                    for row in ready_orders
                }

                selected_order = st.selectbox(
                    "Select order",
                    list(order_options.keys()),
                    key="dispatch_order_select",
                )

                order_id = order_options[selected_order]

                details = get_order_dispatch_details(order_id)

                if details:

                    st.subheader("Order Dispatch Details")

                    st.write(details["order"])

                    with st.form("dispatch_form"):

                        dispatch_date = st.date_input(
                            "Dispatch date",
                            value=date.today(),
                        )

                        st.markdown(
                            "**Products and dispatch quantities**"
                        )

                        dispatch_quantities = {}

                        for item in details["items"]:

                            remaining = int(
                                item["remaining_quantity"]
                            )

                            label = (
                                f"{item['product_name']} — "
                                f"remaining: {remaining} packets"
                            )

                            if remaining > 0:

                                dispatch_quantities[
                                    int(item["product_id"])
                                ] = st.number_input(
                                    label,
                                    min_value=0,
                                    max_value=remaining,
                                    value=0,
                                    step=1,
                                    key=(
                                        f"dispatch_qty_{order_id}_"
                                        f"{item['product_id']}"
                                    ),
                                )

                            else:

                                st.caption(
                                    f"{item['product_name']}: "
                                    f"fully dispatched"
                                )

                        col1, col2 = st.columns(2)

                        with col1:

                            vehicle_number = st.text_input(
                                "Vehicle number"
                            )

                            transporter_name = st.text_input(
                                "Transporter name"
                            )

                            driver_name = st.text_input(
                                "Driver name"
                            )

                        with col2:

                            driver_phone = st.text_input(
                                "Driver phone"
                            )

                            tracking_reference = st.text_input(
                                "Tracking reference"
                            )

                            notes = st.text_input(
                                "Dispatch notes"
                            )

                        submitted = st.form_submit_button(
                            "Create Dispatch"
                        )

                    if submitted:

                        try:

                            dispatch_lines = [
                                (product_id, int(quantity))
                                for product_id, quantity
                                in dispatch_quantities.items()
                                if int(quantity) > 0
                            ]

                            if not dispatch_lines:

                                st.warning(
                                    "Enter a dispatch quantity for "
                                    "at least one product."
                                )

                            else:

                                result = create_dispatch(
                                    order_id,
                                    dispatch_date.isoformat(),
                                    dispatch_lines,
                                    vehicle_number,
                                    transporter_name,
                                    driver_name,
                                    driver_phone,
                                    tracking_reference,
                                    user["user_id"],
                                    notes,
                                )

                                st.success(
                                    "Dispatch created successfully."
                                )

                                st.write(result)

                                st.rerun()

                        except Exception as exc:
                            show_error(exc)

    # ---------------- DISPATCH REGISTER ----------------

    with register_tab:

        dispatches = get_dispatch_register()

        show_table(
            dispatches,
            "No dispatch records available.",
        )

        if dispatches:

            dispatch_options = {
                (
                    f"Dispatch #{row['dispatch_id']} - "
                    f"Order #{row['order_id']}"
                ): row["dispatch_id"]
                for row in dispatches
            }

            selected_dispatch = st.selectbox(
                "Select dispatch",
                list(dispatch_options.keys()),
                key="dispatch_register_select",
            )

            dispatch_id = dispatch_options[selected_dispatch]

            details = get_dispatch_details(dispatch_id)

            st.subheader("Dispatch Details")

            st.write(details)

            if user["role"] != "admin":

                st.info(
                    "Only administrators can update delivery status."
                )

            else:

                with st.form("dispatch_delivery_form"):

                    delivered_date = st.date_input(
                        "Delivery date",
                        value=date.today(),
                    )

                    received_by = st.text_input("Received by")

                    delivery_notes = st.text_area(
                        "Delivery notes"
                    )

                    mark_delivered = st.form_submit_button(
                        "Mark as Delivered"
                    )

                if mark_delivered:

                    try:

                        mark_dispatch_delivered(
                            dispatch_id,
                            delivered_date.isoformat(),
                            received_by,
                            delivery_notes,
                            user["user_id"],
                        )

                        st.success(
                            "Dispatch marked as delivered."
                        )

                        st.rerun()

                    except Exception as exc:
                        show_error(exc)


# ============================================================
# 17. PAYMENT AND RECEIVABLES MANAGEMENT
# ============================================================

def render_payments(user):

    st.header("💰 Payment and Receivables Management")

    record_tab, register_tab, outstanding_tab, overdue_tab = st.tabs(
        [
            "Record Payment",
            "Payment Register",
            "Outstanding",
            "Overdue Invoices",
        ]
    )

    # ---------------- RECORD PAYMENT ----------------

    with record_tab:

        if user["role"] != "admin":

            st.info(
                "Only administrators can record payments."
            )

        else:

            open_invoices = get_open_invoices()

            if not open_invoices:

                st.success(
                    "No outstanding invoices are available."
                )

            else:

                invoice_options = {
                    (
                        f"{row['invoice_number']} - "
                        f"{row['customer_name']} "
                        f"(due {format_rupees(row['outstanding_rupees'])})"
                    ): row
                    for row in open_invoices
                }

                with st.form("payment_form"):

                    selected_invoice_label = st.selectbox(
                        "Invoice",
                        list(invoice_options.keys()),
                    )

                    selected_invoice_row = invoice_options[
                        selected_invoice_label
                    ]

                    payment_date = st.date_input(
                        "Payment date",
                        value=date.today(),
                    )

                    payment_mode = st.selectbox(
                        "Payment mode",
                        [
                            "Cash",
                            "Bank Transfer",
                            "UPI",
                            "Cheque",
                        ],
                    )

                    reference_number = st.text_input(
                        "Transaction/reference number"
                    )

                    outstanding_amount = float(
                        selected_invoice_row["outstanding_rupees"]
                    )

                    amount = st.number_input(
                        "Amount received (₹)",
                        min_value=0.01,
                        max_value=max(0.01, outstanding_amount),
                        value=min(
                            100.0,
                            max(0.01, outstanding_amount),
                        ),
                        step=1.0,
                    )

                    notes = st.text_area("Payment notes")

                    submitted = st.form_submit_button(
                        "Record Payment"
                    )

                if submitted:

                    try:

                        allocations = [
                            (
                                int(
                                    selected_invoice_row["invoice_id"]
                                ),
                                float(amount),
                            )
                        ]

                        record_customer_payment(
                            int(
                                selected_invoice_row["customer_id"]
                            ),
                            payment_date.isoformat(),
                            payment_mode,
                            allocations,
                            user["user_id"],
                            reference_number,
                            notes,
                        )

                        st.success(
                            "Payment recorded successfully."
                        )

                        st.rerun()

                    except Exception as exc:
                        show_error(exc)

    # ---------------- PAYMENT REGISTER ----------------

    with register_tab:

        payments = get_payment_register()

        show_table(
            payments,
            "No payments recorded.",
        )

        if payments:

            payment_options = {
                f"Payment #{row['payment_id']}": row["payment_id"]
                for row in payments
            }

            selected_payment = st.selectbox(
                "Select payment",
                list(payment_options.keys()),
            )

            details = get_payment_details(
                payment_options[selected_payment]
            )

            st.subheader("Payment Details")

            st.write(details)

    # ---------------- OUTSTANDING ----------------

    with outstanding_tab:

        st.subheader("Customer Outstanding Summary")

        show_table(
            get_customer_outstanding_summary(),
            "No outstanding balances.",
        )

    # ---------------- OVERDUE ----------------

    with overdue_tab:

        st.subheader("Overdue Invoices")

        show_table(
            get_overdue_invoices(),
            "No overdue invoices.",
        )


# ============================================================
# 18. PRODUCT COSTING
# ============================================================

def render_costing(user):

    st.header("💹 Product Costing and Profitability")

    rate_tab, costing_tab, register_tab, profitability_tab = st.tabs(
        [
            "Material Cost Rates",
            "Production Costing",
            "Cost Register",
            "Profitability",
        ]
    )

    # ---------------- MATERIAL COST RATES ----------------

    with rate_tab:

        st.subheader("Inventory Cost Rates")

        inventory_items = get_inventory_items()

        if user["role"] == "admin" and inventory_items:

            item_options = {
                (
                    f"{item['item_name']} "
                    f"({item['base_unit']})"
                ): item["item_id"]
                for item in inventory_items
            }

            with st.form("cost_rate_form"):

                selected_item = st.selectbox(
                    "Inventory item",
                    list(item_options.keys()),
                )

                unit_rate = st.number_input(
                    "Cost rate per base unit (₹)",
                    min_value=0.01,
                    value=1.0,
                    step=0.5,
                )

                notes = st.text_area("Notes")

                submitted = st.form_submit_button(
                    "Save Cost Rate"
                )

            if submitted:

                try:

                    set_inventory_cost_rate(
                        item_options[selected_item],
                        unit_rate,
                        user["user_id"],
                        notes,
                    )

                    st.success(
                        "Cost rate saved successfully."
                    )

                    st.rerun()

                except Exception as exc:
                    show_error(exc)

        elif not inventory_items:

            st.info("Register inventory items first.")

        else:

            st.info(
                "Only administrators can update cost rates."
            )

        show_table(
            get_inventory_cost_rates(),
            "No cost rates available.",
        )

    # ---------------- PRODUCTION COSTING ----------------

    with costing_tab:

        st.subheader("Create Production Cost Record")

        if user["role"] != "admin":

            st.info(
                "Only administrators can create costing records."
            )

        else:

            runs = get_uncosted_production_runs()

            if not runs:

                st.success(
                    "All production runs have costing records."
                )

            else:

                run_options = {
                    (
                        f"Run #{row['run_id']} - "
                        f"{row['product_name']}"
                    ): row["run_id"]
                    for row in runs
                }

                selected_run = st.selectbox(
                    "Production run",
                    list(run_options.keys()),
                )

                run_id = run_options[selected_run]

                materials = get_production_run_materials(run_id)

                st.subheader("Material Consumption")

                show_table(materials)

                with st.form("production_costing_form"):

                    labour_cost = st.number_input(
                        "Labour cost (₹)",
                        min_value=0.0,
                        value=0.0,
                    )

                    electricity_cost = st.number_input(
                        "Electricity cost (₹)",
                        min_value=0.0,
                        value=0.0,
                    )

                    other_overhead = st.number_input(
                        "Other manufacturing overhead (₹)",
                        min_value=0.0,
                        value=0.0,
                    )

                    submitted = st.form_submit_button(
                        "Save Production Costing"
                    )

                if submitted:

                    try:

                        create_production_costing(
                            run_id,
                            labour_cost,
                            electricity_cost,
                            other_overhead,
                            user["user_id"],
                        )

                        st.success(
                            "Production costing saved."
                        )

                        st.rerun()

                    except Exception as exc:
                        show_error(exc)

    # ---------------- COST REGISTER ----------------

    with register_tab:

        cost_records = get_production_cost_register()

        show_table(
            cost_records,
            "No production costing records.",
        )

        if cost_records:

            cost_options = {
                (
                    f"Cost Record #{row['costing_id']}"
                ): row["costing_id"]
                for row in cost_records
            }

            selected_cost = st.selectbox(
                "View costing details",
                list(cost_options.keys()),
            )

            details = get_production_cost_details(
                cost_options[selected_cost]
            )

            st.write(details)

    # ---------------- PROFITABILITY ----------------

    with profitability_tab:

        st.subheader("Product Profitability")

        show_table(
            get_product_profitability(),
            "No profitability data available.",
        )


# ============================================================
# 19. AUDIT REPORTS AND MANAGEMENT ANALYTICS
# ============================================================

def render_audit_reports(user):

    st.header("📊 Audit Reports and Management Analytics")

    start_date, end_date = date_range_controls(
        "audit_reports"
    )

    if not check_date_range(start_date, end_date):
        return

    start = start_date.isoformat()
    end = end_date.isoformat()

    (
        dashboard_tab,
        sales_tab,
        purchase_tab,
        inventory_tab,
        production_tab,
        finance_tab,
        audit_tab,
    ) = st.tabs(
        [
            "Dashboard",
            "Sales Reports",
            "Purchase Reports",
            "Inventory Reports",
            "Production Reports",
            "Financial Reports",
            "Audit Activity",
        ]
    )

    # ---------------- DASHBOARD ----------------

    with dashboard_tab:

        st.subheader("Management Summary")

        try:

            summary = get_report_dashboard_summary(
                start,
                end,
            )

            if isinstance(summary, dict):

                metrics = st.columns(4)

                for index, (key, value) in enumerate(summary.items()):

                    metrics[index % 4].metric(
                        key.replace("_", " ").title(),
                        value,
                    )

            else:

                st.write(summary)

        except Exception as exc:
            st.warning(
                f"Unable to load dashboard summary: {exc}"
            )

    # ---------------- SALES REPORTS ----------------

    with sales_tab:

        st.subheader("Sales Report")

        try:

            sales = get_sales_report(
                start,
                end,
            )

            show_table(
                sales,
                "No sales data in this period.",
            )

            st.subheader("Daily Sales")

            daily = get_daily_sales_summary(
                start,
                end,
            )

            show_table(
                daily,
                "No daily sales data.",
            )

            st.subheader("Monthly Sales")

            monthly = get_monthly_sales_summary(
                start,
                end,
            )

            show_table(
                monthly,
                "No monthly sales data.",
            )

        except Exception as exc:
            st.error(f"Sales report error: {exc}")

    # ---------------- PURCHASE REPORTS ----------------

    with purchase_tab:

        st.subheader("Purchase Report")

        try:

            purchases = get_purchase_report(
                start,
                end,
            )

            show_table(
                purchases,
                "No purchase records in this period.",
            )

        except Exception as exc:
            st.error(f"Purchase report error: {exc}")

    # ---------------- INVENTORY REPORTS ----------------

    with inventory_tab:

        st.subheader("Inventory Position")

        try:

            inventory = get_inventory_position_report()

            show_table(
                inventory,
                "No inventory position data.",
            )

            st.subheader("Inventory Movement")

            movements = get_inventory_movement_report(
                start,
                end,
            )

            show_table(
                movements,
                "No inventory movements in this period.",
            )

        except Exception as exc:
            st.error(f"Inventory report error: {exc}")

    # ---------------- PRODUCTION REPORTS ----------------

    with production_tab:

        st.subheader("Production Performance")

        try:

            production = get_production_performance_report(
                start,
                end,
            )

            show_table(
                production,
                "No production records in this period.",
            )

            st.subheader("Material Consumption Variance")

            variance = get_material_variance_report(
                start,
                end,
            )

            show_table(
                variance,
                "No material variance records.",
            )

        except Exception as exc:
            st.error(f"Production report error: {exc}")

    # ---------------- FINANCIAL REPORTS ----------------

    with finance_tab:

        st.subheader("GST Summary")

        try:

            gst = get_gst_summary_report(
                start,
                end,
            )

            show_table(
                gst,
                "No GST records in this period.",
            )

        except Exception as exc:
            st.error(f"GST report error: {exc}")

        st.subheader("Receivables")

        try:

            receivables = get_receivables_report()

            show_table(
                receivables,
                "No receivable records.",
            )

        except Exception as exc:
            st.error(f"Receivables report error: {exc}")

        st.subheader("Product Profitability")

        try:

            profitability = get_profitability_report()

            show_table(
                profitability,
                "No profitability records.",
            )

        except Exception as exc:
            st.error(f"Profitability report error: {exc}")

        st.subheader("Excel Report Export")

        if st.button(
            "Generate Excel Report",
            use_container_width=True,
        ):

            try:

                excel_file = generate_excel_report(
                    start,
                    end,
                )

                st.download_button(
                    label="Download Excel Report",
                    data=excel_file,
                    file_name=(
                        f"FactoryFlow_Audit_Report_"
                        f"{start}_to_{end}.xlsx"
                    ),
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                )

            except Exception as exc:
                st.error(f"Excel export failed: {exc}")

    # ---------------- AUDIT ACTIVITY ----------------

    with audit_tab:

        st.subheader("User Activity Audit Trail")

        try:

            activity = get_user_activity_report(
                start,
                end,
            )

            show_table(
                activity,
                "No user activity recorded in this period.",
            )

        except Exception as exc:
            st.error(f"Audit activity report error: {exc}")


# ============================================================
# 20. ROLE-BASED NAVIGATION
# ============================================================

ROLE_PAGES = {

    "admin": [
        "Dashboard",
        "User Management",
        "Master Data",
        "BOM Management",
        "Inventory & Purchases",
        "Production Management",
        "Sales Orders",
        "Invoicing & Billing",
        "Dispatch & Delivery",
        "Payment & Receivables",
        "Product Costing",
        "Audit Reports",
    ],

    "salesman": [
        "Dashboard",
        "Sales Orders",
    ],

    "production": [
        "Dashboard",
        "BOM Management",
        "Inventory & Purchases",
        "Production Management",
    ],

    "owner": [
        "Dashboard",
        "Master Data",
        "BOM Management",
        "Inventory & Purchases",
        "Production Management",
        "Sales Orders",
        "Invoicing & Billing",
        "Dispatch & Delivery",
        "Payment & Receivables",
        "Product Costing",
        "Audit Reports",
    ],

    "auditor": [
        "Dashboard",
        "BOM Management",
        "Inventory & Purchases",
        "Production Management",
        "Sales Orders",
        "Invoicing & Billing",
        "Dispatch & Delivery",
        "Payment & Receivables",
        "Product Costing",
        "Audit Reports",
    ],
}


# ============================================================
# 21. APPLICATION ENTRY POINT
# ============================================================

def main():

    show_header()

    # First-time setup

    if count_users() == 0:

        render_initial_admin_setup()
        show_footer()
        return

    # Login

    if "current_user" not in st.session_state:

        render_login()
        show_footer()
        return

    user = st.session_state["current_user"]

    allowed_pages = ROLE_PAGES.get(
        user["role"],
        ["Dashboard"],
    )

    # Sidebar

    with st.sidebar:

        st.title("🏭 FactoryFlow")

        st.caption("Order-to-Audit Management System")

        st.divider()

        st.write("Signed in as")

        st.markdown(
            f"**{user['full_name']}**"
        )

        st.caption(
            f"Role: {user['role'].upper()}"
        )

        st.divider()

        selected_page = st.radio(
            "Navigation",
            allowed_pages,
        )

        st.divider()

        if st.button(
            "🚪 Logout",
            use_container_width=True,
        ):

            st.session_state.pop(
                "current_user",
                None,
            )

            st.rerun()

    # --------------------------------------------------------
    # PAGE ROUTING
    # --------------------------------------------------------

    if selected_page == "Dashboard":

        render_dashboard(user)

    elif selected_page == "User Management":

        render_user_management(user)

    elif selected_page == "Master Data":

        render_master_data(user)

    elif selected_page == "BOM Management":

        render_bom_management(user)

    elif selected_page == "Inventory & Purchases":

        render_inventory_purchases(user)

    elif selected_page == "Production Management":

        render_production_management(user)

    elif selected_page == "Sales Orders":

        render_sales_orders(user)

    elif selected_page == "Invoicing & Billing":

        render_invoicing(user)

    elif selected_page == "Dispatch & Delivery":

        render_dispatch_management(user)

    elif selected_page == "Payment & Receivables":

        render_payments(user)

    elif selected_page == "Product Costing":

        render_costing(user)

    elif selected_page == "Audit Reports":

        render_audit_reports(user)

    else:

        st.error("Page not found.")

    show_footer()


# ============================================================
# 22. RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    main()