# 🏭 FactoryFlow
### Order-to-Audit Management System for Food Manufacturers

FactoryFlow is a web-based management system developed using Python and Streamlit to streamline business operations in food manufacturing companies.

The application integrates inventory management, purchasing, production planning, sales order processing, GST invoicing, dispatch management, payment tracking, product costing and audit reporting into a centralized platform.

The goal of FactoryFlow is to improve operational visibility, maintain accurate inventory records, simplify financial tracking and support better business decision-making.

---

## 📌 Project Overview

Food manufacturing businesses handle multiple interconnected operations, from purchasing raw materials to manufacturing finished products and delivering them to customers.

Managing these activities separately can lead to inventory discrepancies, delayed order processing, inaccurate costing and difficulties in maintaining financial records.

FactoryFlow provides a centralized application to manage the complete order-to-audit workflow.

### Key Objectives

- Centralize manufacturing and business operations.
- Maintain accurate inventory and stock movement records.
- Manage Bills of Materials (BOM) and production activities.
- Simplify customer sales order processing.
- Generate GST-based invoices.
- Track product dispatches and customer payments.
- Calculate production costs and product profitability.
- Provide management reports and audit information.
- Implement role-based access control.

---

## ✨ Features and Modules

### 1. User Authentication and Access Control
- Secure user login.
- Password hashing using Argon2.
- Initial administrator account setup.
- Role-based access control.
- User account management.

### 2. Master Data Management
- Customer registration.
- Supplier registration.
- Inventory item management.
- Finished product registration.
- GST and HSN information management.

### 3. Bill of Materials (BOM) Management
- Create product-specific BOMs.
- Define raw material requirements.
- Specify packaging material requirements.
- Manage expected production batch yields.
- View registered BOM recipes.

### 4. Inventory and Purchase Management
- Record opening inventory.
- Maintain stock movement records.
- Record supplier purchases.
- Track inventory balances.
- View stock movement ledger.
- Monitor inventory availability.

### 5. Production Management
- Select active BOMs.
- Plan production batches.
- Record actual material consumption.
- Record good production output.
- Track damaged pouches.
- Record cartons used.
- Review production history.

### 6. Sales Order Management
- Create customer sales orders.
- Add multiple products to an order.
- Calculate order values.
- Review stock availability.
- Approve or reject sales orders.
- Maintain order history.

### 7. GST Invoicing and Billing
- Generate invoices from approved sales orders.
- Generate financial-year-based invoice numbers.
- Calculate taxable values.
- Calculate CGST and SGST for intra-state transactions.
- Calculate IGST for inter-state transactions.
- Maintain invoice registers.
- View invoice details.

### 8. Dispatch and Delivery Management
- Create dispatch records.
- Record product-wise dispatch quantities.
- Maintain vehicle and transporter details.
- Record driver information.
- Generate delivery challan references.
- Deduct dispatched goods from inventory.
- Track delivery completion.

### 9. Payment and Receivables Management
- Record customer payments.
- Support cash, UPI, cheque and bank transfer.
- Allocate payments against invoices.
- View payment records.
- Monitor outstanding balances.
- Identify overdue invoices.

### 10. Product Costing and Profitability
- Maintain inventory cost rates.
- Record production labour costs.
- Record electricity costs.
- Record other manufacturing overheads.
- Calculate production costs.
- Review product profitability.

### 11. Audit Reports and Management Analytics
- Sales reports.
- Daily and monthly sales summaries.
- Purchase reports.
- Inventory position reports.
- Inventory movement reports.
- Production performance reports.
- Material consumption variance reports.
- GST summary reports.
- Receivables reports.
- Product profitability reports.
- User activity audit trail.
- Excel report generation.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core programming language |
| Streamlit | Web application interface |
| SQLite | Database management |
| Pandas | Data processing and reporting |
| Plotly | Data visualization |
| Argon2 | Password hashing |
| ReportLab | PDF generation support |
| OpenPyXL | Excel report handling |
| Pytest | Testing framework |

---

## 📁 Project Structure

```text
NIT_CDI_Order_Audit_System/
│
├── .streamlit/
│   └── config.toml
│
├── app.py
│
├── database.py
│
├── requirements.txt
│
├── README.md
│
├── data/
│
├── exports/
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
└── tests/
    └── test_module_integrity.py
```

---

## ⚙️ Installation and Setup

Follow these instructions to run FactoryFlow on your local machine.

### Prerequisites

Install the following:

- Python 3.10 or later.
- Visual Studio Code (recommended).
- Git (optional, for version control).

### Step 1: Clone the Repository

Open your terminal and execute:

```bash
git clone https://github.com/nithyasri11-dev/FactoryFlow-Order-to-Audit-System.git
```

Navigate into the project folder:

```bash
cd FactoryFlow-Order-to-Audit-System
```

### Step 2: Create a Virtual Environment

```bash
python -m venv .venv
```

### Step 3: Activate the Virtual Environment

For Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

For Windows Command Prompt:

```cmd
.venv\Scripts\activate
```

### Step 4: Install Dependencies

```bash
python -m pip install --upgrade pip
```

```bash
pip install -r requirements.txt
```

### Step 5: Run the Application

```bash
python -m streamlit run app.py
```

### Step 6: Open the Application

Open the following address in your web browser:

```text
http://localhost:8501
```

On the first run, create an administrator account if the database contains no registered users.

Log in using the administrator credentials to access the application.

---

## 📦 Dependencies

The project dependencies are maintained in `requirements.txt`.

```text
streamlit>=1.35
pandas>=2.0
plotly>=5.18
reportlab>=4.0
argon2-cffi>=23.1
openpyxl>=3.1
pytest>=8.0
```

Install them using:

```bash
pip install -r requirements.txt
```

---

## 🔄 Business Workflow

FactoryFlow follows an integrated manufacturing and order-processing workflow.

```text
Customer and Supplier Registration
               |
               v
       Product Registration
               |
               v
      BOM Configuration
               |
               v
    Opening Stock and Purchases
               |
               v
     Production Management
               |
               v
       Sales Order Creation
               |
               v
       Sales Order Approval
               |
               v
        GST Invoice Creation
               |
               v
        Product Dispatch
               |
               v
       Customer Payment
               |
               v
       Production Costing
               |
               v
     Audit and Business Reports
```

---

## 👥 User Roles

FactoryFlow supports five user roles.

| Role | Responsibilities |
|---|---|
| Admin | Overall application administration and business operations |
| Salesman | Customer sales order creation |
| Production | BOM, inventory and production operations |
| Owner | Business monitoring and management oversight |
| Auditor | Review of operational and financial information |

Access to individual operations is controlled through role-based permissions.

---

## 🧪 Running Tests

The project includes a structural integrity test.

Execute:

```bash
python -m pytest tests/test_module_integrity.py -v
```

You can also check Python syntax using:

```bash
python -m compileall -q app.py database.py modules tests
```

These checks do not replace full end-to-end application testing.

---

## 💾 Database Information

FactoryFlow uses SQLite for local data storage.

The database is created automatically at:

```text
data/factoryflow.db
```

Database tables are initialized when the application starts.

The database contains operational information such as:

- User accounts.
- Customers and suppliers.
- Inventory items and products.
- Bills of Materials.
- Purchases and stock movements.
- Production runs.
- Sales orders.
- GST invoices.
- Dispatch records.
- Customer payments.
- Costing records.
- Audit logs.

**Important:** Back up the database regularly. Do not upload database files containing sensitive business information to a public GitHub repository.

---

## 🚀 Deployment

FactoryFlow is developed as a Streamlit application and can be deployed using Streamlit Community Cloud.

Deployment platform:

https://share.streamlit.io/

Select the GitHub repository, choose the `main` branch and specify:

```text
Main file path: app.py
```

Install the dependencies using the repository's `requirements.txt`.

**Deployment consideration:** The current application uses a local SQLite database. Local file storage on hosted platforms may not provide reliable long-term persistence. A persistent external database is recommended before using the application for real business operations.

---

## 🔐 Security Considerations

- User passwords are hashed rather than stored as plain text.
- Application access is controlled by user roles.
- Database operations use parameterized SQL queries.
- Database files and configuration secrets should not be committed to GitHub.
- The application is intended as an educational prototype and requires further security validation before production use.

---

## 🔮 Future Enhancements

Potential future improvements include:

- Integration with a cloud-hosted database.
- PDF GST invoice and delivery challan downloads.
- Advanced inventory forecasting.
- Automated low-stock notifications.
- Barcode and QR-code integration.
- Production scheduling and planning.
- Advanced analytics dashboards.
- Email notifications for order and payment updates.
- Multi-location warehouse management.

---

## 👩‍💻 Project Information

**Project Name:** FactoryFlow – Order-to-Audit Management System for Food Manufacturers

**Development Platform:** Python and Streamlit

**Database:** SQLite

**Project Type:** Web-Based Business Management Application

**Repository:**  
https://github.com/nithyasri11-dev/FactoryFlow-Order-to-Audit-System

---

## 📄 License

This project is developed for educational and demonstration purposes.

A formal open-source license can be added if the project is intended for public reuse.

---

## 🙌 Acknowledgement

FactoryFlow demonstrates the application of Python programming, database management, business process automation and data analytics to food manufacturing operations.

The project aims to provide an integrated digital solution for managing manufacturing activities from raw material procurement to final business audit reporting.