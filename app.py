from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session
import mysql.connector
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from dotenv import load_dotenv
from datetime import timedelta
import os
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # Set a strong secret key
app.permanent_session_lifetime = timedelta(minutes=30)

# MySQL config
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "03001Cm0#!")

# Utility function to validate names
def sanitize_name(name):
    return re.match(r'^[a-zA-Z0-9_]+$', name) is not None

# Get all user databases (except system ones)
def get_databases():
    try:
        conn = mysql.connector.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD)
        cursor = conn.cursor()
        cursor.execute("SHOW DATABASES;")
        databases = [db[0] for db in cursor.fetchall() if db[0] not in ["information_schema", "mysql", "performance_schema", "sys"]]
        conn.close()
        return databases
    except mysql.connector.Error as err:
        print(f"❌ ERROR: {err}")
        return []

# Get tables from a specific database
def get_tables(database_name):
    if not sanitize_name(database_name):
        return []
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=database_name
        )
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES;")
        tables = [table[0] for table in cursor.fetchall()]
        conn.close()
        return tables
    except mysql.connector.Error as err:
        print(f"❌ ERROR: {err}")
        return []

# Fetch table data with optional date filters
def fetch_table_data(database_name, table_name, start_date=None, end_date=None):
    if not sanitize_name(database_name) or not sanitize_name(table_name):
        return None

    date_column_name = "date_time"
    where_clause = []

    if start_date:
        where_clause.append(f"`{date_column_name}` >= '{start_date} 00:00:00'")
    if end_date:
        where_clause.append(f"`{date_column_name}` <= '{end_date} 23:59:59'")

    where_clause_str = " AND ".join(where_clause)

    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=database_name
        )
        query = f"SELECT * FROM `{table_name}`"
        if where_clause_str:
            query += f" WHERE {where_clause_str}"
        query += f" ORDER BY `{date_column_name}` ASC"

        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except mysql.connector.Error as err:
        print(f"❌ ERROR: {err}")
        return None

# -------------------- ROUTES --------------------

@app.route('/')
def index():
    databases = get_databases()
    return render_template('index.html', databases=databases)

@app.route('/home')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/our-work')
def our_work():
    return render_template('our_work.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# 🔐 Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        userid = request.form['userid']
        password = request.form['password']
        if userid == 'admin' and password == 'admin':
            session.permanent = True
            session['user'] = userid
            return redirect(url_for('data'))
        else:
            error = 'Invalid Credentials. Please try again.'
    return render_template('login.html', error=error)

# 🔓 Logout route
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

# 🔐 Protected data route
@app.route('/data')
def data():
    if 'user' not in session:
        return redirect(url_for('login'))
    databases = get_databases()
    return render_template('1index.html', databases=databases)

# AJAX route for dynamic table loading
@app.route('/get_tables', methods=['POST'])
def get_tables_route():
    database_name = request.json.get('database_name')
    tables = get_tables(database_name)
    return jsonify(tables)

# Page to choose export options
@app.route('/export_options/<database_name>/<table_name>')
def export_options(database_name, table_name):
    if not sanitize_name(database_name) or not sanitize_name(table_name):
        return "<h3>Invalid input.</h3>"
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    return render_template('export_options.html',
                           database_name=database_name,
                           table_name=table_name,
                           start_date=start_date,
                           end_date=end_date)

# File download (CSV, Excel, PDF)
@app.route('/download/<database_name>/<table_name>/<format>')
def download_file(database_name, table_name, format):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    df = fetch_table_data(database_name, table_name, start_date, end_date)
    if df is None or df.empty:
        return "<h3>No data available for this table.</h3>"

    file_path = f"{table_name}.{format}"

    if format == "csv":
        df.to_csv(file_path, index=False)
    elif format == "xlsx":
        df.to_excel(file_path, index=False, engine="openpyxl")
    elif format == "pdf":
        file_path = f"{table_name}.pdf"
        generate_pdf(df, file_path)

    return send_file(file_path, as_attachment=True)

# PDF generation logic
def generate_pdf(df, file_path):
    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    c.setFont("Helvetica", 9)

    x_offset = 30
    y_offset = height - 40
    row_height = 20

    def draw_page(dataframe):
        nonlocal y_offset
        c.drawString(x_offset, y_offset, "Table Data")
        y_offset -= 20

        # Draw headers
        x = x_offset
        for col in dataframe.columns:
            c.drawString(x, y_offset, str(col))
            x += 100
        y_offset -= row_height

        for _, row in dataframe.iterrows():
            x = x_offset
            for cell in row:
                c.drawString(x, y_offset, str(cell)[:15])
                x += 100
            y_offset -= row_height
            if y_offset < 40:
                c.showPage()
                c.setFont("Helvetica", 9)
                y_offset = height - 40

    draw_page(df)
    c.save()

# -------------------- Run App --------------------
if __name__ == '__main__':
    app.run(debug=True)
