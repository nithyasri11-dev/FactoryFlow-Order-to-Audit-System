import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "factoryflow.db"


def get_connection():
    """Connect to the FactoryFlow SQLite database."""

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        DB_PATH,
        timeout=30,
    )

    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def initialize_database():
    """Create the core FactoryFlow database tables."""

    schema = """

    -- =====================================================
    -- USERS AND ACCESS CONTROL
    -- =====================================================

    CREATE TABLE IF NOT EXISTS users (

        user_id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE NOT NULL,

        full_name TEXT NOT NULL,

        password_hash TEXT NOT NULL,

        role TEXT NOT NULL CHECK (
            role IN (
                'salesman',
                'admin',
                'production',
                'owner',
                'auditor'
            )
        ),

        active INTEGER DEFAULT 1,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP

    );


    -- =====================================================
    -- CUSTOMERS
    -- =====================================================

    CREATE TABLE IF NOT EXISTS customers (

        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,

        customer_name TEXT NOT NULL,

        customer_type TEXT NOT NULL,

        gstin TEXT,

        state TEXT NOT NULL,

        phone TEXT,

        address TEXT,

        active INTEGER DEFAULT 1

    );


    -- =====================================================
    -- SUPPLIERS
    -- =====================================================

    CREATE TABLE IF NOT EXISTS suppliers (

        supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,

        supplier_name TEXT NOT NULL,

        gstin TEXT,

        state TEXT,

        phone TEXT,

        address TEXT

    );


    -- =====================================================
    -- INVENTORY MASTER
    -- =====================================================

    CREATE TABLE IF NOT EXISTS inventory_items (

        item_id INTEGER PRIMARY KEY AUTOINCREMENT,

        item_code TEXT UNIQUE NOT NULL,

        item_name TEXT NOT NULL,

        category TEXT NOT NULL CHECK (
            category IN (
                'raw_material',
                'packaging_material',
                'finished_good'
            )
        ),

        base_unit TEXT NOT NULL,

        reorder_level_milli INTEGER DEFAULT 0,

        active INTEGER DEFAULT 1

    );


    -- =====================================================
    -- FINISHED PRODUCTS
    -- =====================================================

    CREATE TABLE IF NOT EXISTS products (

        product_id INTEGER PRIMARY KEY AUTOINCREMENT,

        inventory_item_id INTEGER UNIQUE NOT NULL,

        product_name TEXT NOT NULL,

        pack_size_g INTEGER NOT NULL,

        selling_price_paise INTEGER NOT NULL,

        gst_rate_bps INTEGER DEFAULT 500,

        hsn_code TEXT,

        FOREIGN KEY (inventory_item_id)
            REFERENCES inventory_items(item_id)

    );


    -- =====================================================
    -- BILL OF MATERIALS
    -- =====================================================

    CREATE TABLE IF NOT EXISTS boms (

        bom_id INTEGER PRIMARY KEY AUTOINCREMENT,

        product_id INTEGER NOT NULL,

        version INTEGER DEFAULT 1,

        expected_yield_packets INTEGER NOT NULL,

        active INTEGER DEFAULT 1,

        FOREIGN KEY (product_id)
            REFERENCES products(product_id),

        UNIQUE(product_id, version)

    );


    CREATE TABLE IF NOT EXISTS bom_items (

        bom_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

        bom_id INTEGER NOT NULL,

        inventory_item_id INTEGER NOT NULL,

        quantity_per_batch_milli INTEGER NOT NULL,

        FOREIGN KEY (bom_id)
            REFERENCES boms(bom_id),

        FOREIGN KEY (inventory_item_id)
            REFERENCES inventory_items(item_id)

    );


    -- =====================================================
    -- PURCHASES
    -- =====================================================

    CREATE TABLE IF NOT EXISTS purchases (

        purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,

        supplier_id INTEGER NOT NULL,

        invoice_reference TEXT,

        purchase_date TEXT DEFAULT CURRENT_TIMESTAMP,

        status TEXT DEFAULT 'draft',

        FOREIGN KEY (supplier_id)
            REFERENCES suppliers(supplier_id)

    );


    CREATE TABLE IF NOT EXISTS purchase_items (

        purchase_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

        purchase_id INTEGER NOT NULL,

        inventory_item_id INTEGER NOT NULL,

        quantity_milli INTEGER NOT NULL,

        unit_rate_paise INTEGER NOT NULL,

        total_amount_paise INTEGER NOT NULL,

        FOREIGN KEY (purchase_id)
            REFERENCES purchases(purchase_id),

        FOREIGN KEY (inventory_item_id)
            REFERENCES inventory_items(item_id)

    );


    -- =====================================================
    -- CENTRAL STOCK LEDGER
    -- =====================================================

    CREATE TABLE IF NOT EXISTS stock_movements (

        movement_id INTEGER PRIMARY KEY AUTOINCREMENT,

        inventory_item_id INTEGER NOT NULL,

        quantity_delta_milli INTEGER NOT NULL,

        movement_type TEXT NOT NULL,

        source_type TEXT NOT NULL,

        source_id INTEGER,

        created_by INTEGER,

        notes TEXT,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (inventory_item_id)
            REFERENCES inventory_items(item_id),

        FOREIGN KEY (created_by)
            REFERENCES users(user_id)

    );


    -- =====================================================
    -- PRODUCTION
    -- =====================================================

    CREATE TABLE IF NOT EXISTS production_runs (

        run_id INTEGER PRIMARY KEY AUTOINCREMENT,

        product_id INTEGER NOT NULL,

        bom_id INTEGER NOT NULL,

        batch_count_milli INTEGER NOT NULL,

        expected_output_packets INTEGER NOT NULL,

        actual_good_packets INTEGER,

        damaged_pouches INTEGER DEFAULT 0,

        cartons_used INTEGER DEFAULT 0,

        status TEXT DEFAULT 'draft',

        production_date TEXT DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (product_id)
            REFERENCES products(product_id),

        FOREIGN KEY (bom_id)
            REFERENCES boms(bom_id)

    );


    CREATE TABLE IF NOT EXISTS production_consumptions (

        consumption_id INTEGER PRIMARY KEY AUTOINCREMENT,

        run_id INTEGER NOT NULL,

        inventory_item_id INTEGER NOT NULL,

        planned_quantity_milli INTEGER NOT NULL,

        actual_quantity_milli INTEGER NOT NULL,

        unit_rate_paise INTEGER DEFAULT 0,

        total_cost_paise INTEGER DEFAULT 0,

        FOREIGN KEY (run_id)
            REFERENCES production_runs(run_id),

        FOREIGN KEY (inventory_item_id)
            REFERENCES inventory_items(item_id)

    );


    CREATE TABLE IF NOT EXISTS production_overheads (

        overhead_id INTEGER PRIMARY KEY AUTOINCREMENT,

        run_id INTEGER NOT NULL,

        overhead_type TEXT NOT NULL,

        amount_paise INTEGER NOT NULL,

        notes TEXT,

        FOREIGN KEY (run_id)
            REFERENCES production_runs(run_id)

    );


    -- =====================================================
    -- AUDIT TRAIL
    -- =====================================================

    CREATE TABLE IF NOT EXISTS audit_logs (

        log_id INTEGER PRIMARY KEY AUTOINCREMENT,

        user_id INTEGER,

        action TEXT NOT NULL,

        entity_type TEXT NOT NULL,

        entity_id INTEGER,

        details TEXT,

        created_at TEXT DEFAULT CURRENT_TIMESTAMP,

        FOREIGN KEY (user_id)
            REFERENCES users(user_id)

    );


    -- =====================================================
    -- STOCK BALANCE VIEW
    -- =====================================================

    CREATE VIEW IF NOT EXISTS stock_balances AS

    SELECT

        inventory_item_id,

        SUM(quantity_delta_milli) AS balance_milli

    FROM stock_movements

    GROUP BY inventory_item_id;


    -- =====================================================
    -- PERFORMANCE INDEXES
    -- =====================================================

    CREATE INDEX IF NOT EXISTS idx_stock_item

    ON stock_movements(inventory_item_id);


    CREATE INDEX IF NOT EXISTS idx_production_date

    ON production_runs(production_date);


    CREATE INDEX IF NOT EXISTS idx_purchase_date

    ON purchases(purchase_date);

    """

    with get_connection() as conn:

        conn.executescript(schema)

        conn.commit()


if __name__ == "__main__":

    initialize_database()

    print(
        "FactoryFlow database created successfully!"
    )

    print(
        f"Database location: {DB_PATH}"
    )