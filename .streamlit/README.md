# FactoryFlow – Order-to-Audit Management System for Food Manufacturers

## 1. Project Overview

FactoryFlow is a Streamlit-based management system designed for food manufacturing businesses. It supports the order-to-audit workflow by connecting sales, inventory, procurement, production, invoicing, dispatch, payments, product costing, and audit reporting.

The application aims to improve operational visibility, maintain transaction records, and support business decision-making.

## 2. Key Modules

- **Authentication and User Management:** User login and role-based access.
- **Master Data Management:** Customers, suppliers, inventory items, and finished products.
- **Bill of Materials (BOM):** Manage product recipes and material requirements.
- **Inventory and Purchases:** Record opening stock, purchases, and stock movements.
- **Production Management:** Record production runs and material consumption.
- **Sales Orders:** Create and manage customer orders.
- **GST Invoicing:** Generate invoices for eligible sales orders.
- **Dispatch and Delivery:** Manage dispatch records and delivery status.
- **Payments and Receivables:** Record customer payments and monitor outstanding balances.
- **Product Costing:** Calculate production costs and product profitability.
- **Audit Reports:** Generate operational, financial, inventory, and GST reports.

## 3. Technology Stack

- Python
- Streamlit
- SQLite
- Pandas
- Plotly
- ReportLab
- Argon2
- OpenPyXL
- Pytest

## 4. Project Structure

```text
NIT_CDI_Order_Audit_System/
│
├── .streamlit/
│   └── config.toml
│
├── app.py
├── database.py
├── requirements.txt
├── README.md
│
├── data/
│
├── modules/
│   ├── __init__.py
│   ├── authentication.py
│   ├── masters.py
│   ├── bom.py
│   ├── inventory.py
│   ├── production.py
│   ├── sales.py
│   ├── invoicing.py
│   ├── dispatch.py
│   ├── payments.py
│   ├── costing.py
│   └── reports.py
│
├── exports/
│
└── tests/
    └── test_module_integrity.py
```

## 5. Installation

### Step 1: Install Python

Install a compatible Python version on your computer.

### Step 2: Open the project directory

Open a terminal in the project folder.

### Step 3: Create a virtual environment

```bash
python -m venv .venv
```

### Step 4: Activate the environment

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### Step 5: Install dependencies

```bash
pip install -r requirements.txt
```

## 6. Running the Application

From the project directory, execute:

```bash
streamlit run app.py
```

The application should open in your browser at:

```text
http://localhost:8501
```

Follow the application's initial setup process to create the first administrator account, if that setup screen is implemented in your installed version.

## 7. Testing

Run the available module-integrity tests using:

```bash
python -m pytest tests/test_module_integrity.py -v
```

These tests provide an initial structural check. They do not replace database integration tests or complete end-to-end workflow testing.

## 8. Data and Security

- Keep database files and backups secure.
- Do not commit passwords, API keys, or secret configuration files to version control.
- Use appropriate access permissions for each user role.
- Back up business data regularly.
- Validate financial, inventory, and GST calculations before using the system for actual business transactions.

## 9. Project Objective

The objective of FactoryFlow is to provide an integrated platform for managing food manufacturing operations, from customer order creation through production, billing, delivery, payment collection, costing, and audit reporting.