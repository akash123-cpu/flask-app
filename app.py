from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, abort
import pandas as pd
import os
from io import BytesIO
from fpdf import FPDF
from dotenv import load_dotenv
from functools import wraps

# Google Drive imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_secret_key_here')

station_master_df = pd.read_excel('station_master.xlsx')

DATA_FOLDER = 'data'
REPORT_FOLDER = os.path.join(DATA_FOLDER, 'report')

USE_GOOGLE_DRIVE = os.getenv('USE_GOOGLE_DRIVE', 'False').lower() == 'true'
GOOGLE_DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')

drive_service = None

if USE_GOOGLE_DRIVE:
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    drive_service = build('drive', 'v3', credentials=credentials)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def find_csv_path(logger_id):
    filename = f"{logger_id}_enriched.csv"
    if USE_GOOGLE_DRIVE:
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and name = '{filename}' and trashed = false"
        response = drive_service.files().list(q=query, fields="files(id, name)").execute()
        files = response.get('files', [])
        if not files:
            app.logger.warning(f"File {filename} not found in Google Drive folder.")
            return None
        return files[0]['id']
    else:
        for root, _, files in os.walk(DATA_FOLDER):
            for file in files:
                if file == filename:
                    return os.path.join(root, file)
        app.logger.warning(f"File {filename} not found in local folder.")
        return None

def load_csv_from_drive(file_id):
    request = drive_service.files().get_media(fileId=file_id)
    fh = BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    df = pd.read_csv(fh, low_memory=False)
    return df

def load_csv(logger_id):
    file_path_or_id = find_csv_path(logger_id)
    if not file_path_or_id:
        app.logger.error(f"CSV file for logger_id {logger_id} not found.")
        return None
    try:
        if USE_GOOGLE_DRIVE:
            df = load_csv_from_drive(file_path_or_id)
        else:
            df = pd.read_csv(file_path_or_id, low_memory=False)
        df = parse_datetime_column(df)
        return df
    except Exception as e:
        app.logger.error(f"Error loading CSV for {logger_id}: {e}")
        return None

def parse_datetime_column(df):
    df['date_time'] = pd.to_datetime(df['date_time'], format="%d/%m/%y %H:%M", errors='coerce')
    df.dropna(subset=['date_time'], inplace=True)
    return df

# -------- Routes -------- #

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/our_work')
def our_work():
    return render_template('our_work.html')

@app.route('/contact')
def contact():
    success = request.args.get('success', False)
    return render_template('contact.html', success=success)

@app.route('/submit_contact', methods=['POST'])
def submit_contact():
    name = request.form.get('name')
    email = request.form.get('email')
    phone = request.form.get('phone')
    message = request.form.get('message')
    app.logger.info(f"Contact form submitted: Name={name}, Email={email}, Phone={phone}, Message={message}")
    return render_template('contact.html', success=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'admin':
            session['user_id'] = username
            return redirect(url_for('data'))
        else:
            return render_template('login.html', error="Invalid username or password")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/data')
@login_required
def data():
    database_names = sorted(station_master_df['Database Name'].unique())
    return render_template('1index.html', database_names=database_names)

@app.route('/index')
@login_required
def index():
    database_names = sorted(station_master_df['Database Name'].unique())
    return render_template('1index.html', database_names=database_names)

@app.route('/dashboard')
@login_required
def dashboard():
    labels = pd.date_range(end=pd.Timestamp.today(), periods=7).strftime('%Y-%m-%d').tolist()
    counts = [5, 9, 7, 8, 4, 6, 10]
    try:
        summary_df = pd.read_excel(os.path.join(REPORT_FOLDER, 'mechatronics_summary.xlsx'))
        station_df = pd.read_excel(os.path.join(REPORT_FOLDER, 'station_details_by_agency.xlsx'))
        summary_html = summary_df.to_html(classes='table table-bordered table-sm', index=False)
        station_html = station_df.to_html(classes='table table-bordered table-sm', index=False)
    except Exception as e:
        summary_html = f"<div class='alert alert-danger'>Failed to load summary: {e}</div>"
        station_html = f"<div class='alert alert-danger'>Failed to load station details: {e}</div>"
    return render_template('dashboard.html',
                           labels=labels,
                           counts=counts,
                           summary_table=summary_html,
                           station_table=station_html)

@app.route('/download_report/<filename>')
@login_required
def download_report(filename):
    safe_files = {'mechatronics_summary.xlsx', 'station_details_by_agency.xlsx'}
    if filename not in safe_files:
        abort(403, description="Access forbidden")
    path = os.path.join(REPORT_FOLDER, filename)
    if not os.path.exists(path):
        abort(404, description="File not found")
    return send_file(path, as_attachment=True)

@app.route('/get_station_logger_info', methods=['POST'])
@login_required
def get_station_logger_info():
    db = request.form.get('database_name')
    selected_logger_id = request.form.get('logger_id')
    selected_station_name = request.form.get('station_name')

    filtered = station_master_df[station_master_df['Database Name'] == db]

    if selected_logger_id:
        matched_row = filtered[filtered['Data Logger ID'].astype(str) == selected_logger_id]
        if not matched_row.empty:
            selected_station_name = matched_row['Station Name'].values[0]
    elif selected_station_name:
        matched_row = filtered[filtered['Station Name'] == selected_station_name]
        if not matched_row.empty:
            selected_logger_id = matched_row['Data Logger ID'].astype(str).values[0]

    station_names = sorted(filtered['Station Name'].unique())
    logger_ids = sorted(filtered['Data Logger ID'].astype(str).unique())

    return jsonify({
        "station_names": station_names,
        "logger_ids": logger_ids,
        "selected_station_name": selected_station_name,
        "selected_logger_id": selected_logger_id
    })

@app.route('/get_dates', methods=['POST'])
@login_required
def get_dates():
    logger_id = request.form.get('logger_id')
    df = load_csv(logger_id)
    if df is None:
        return jsonify([])
    dates = df['date_time'].dt.date.unique()
    return jsonify([str(d) for d in sorted(dates)])

@app.route('/get_data', methods=['POST'])
@login_required
def get_data():
    logger_id = request.form.get('logger_id')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    df = load_csv(logger_id)
    if df is None:
        return "CSV file not found", 404

    start = pd.to_datetime(start_date).date()
    end = pd.to_datetime(end_date).date()
    mask = (df['date_time'].dt.date >= start) & (df['date_time'].dt.date <= end)
    df_filtered = df.loc[mask]

    if df_filtered.empty:
        return "<div class='alert alert-warning'>No data found for the selected date range.</div>"

    unique_dates = sorted(df_filtered['date_time'].dt.date.unique())
    if len(unique_dates) > 4:
        last_4_dates = unique_dates[-4:]
        df_filtered = df_filtered[df_filtered['date_time'].dt.date.isin(last_4_dates)]

    return df_filtered.to_html(classes='table table-striped table-bordered data-table', index=False)

def get_filtered_df(logger_id, start_date, end_date):
    df = load_csv(logger_id)
    if df is None:
        return None
    mask = (df['date_time'].dt.date >= pd.to_datetime(start_date).date()) & \
           (df['date_time'].dt.date <= pd.to_datetime(end_date).date())
    return df.loc[mask]

def send_dataframe_as_file(df, logger_id, start_date, end_date, file_type='csv'):
    output = BytesIO()
    filename = f"{logger_id}_{start_date}_to_{end_date}.{file_type}"
    try:
        if file_type == 'csv':
            df.to_csv(output, index=False)
            mimetype = 'text/csv'
        elif file_type == 'xlsx':
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Data')
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        else:
            abort(400, description="Unsupported file type")
        output.seek(0)
        return send_file(output, mimetype=mimetype, as_attachment=True, download_name=filename)
    except Exception as e:
        app.logger.error(f"Error sending {file_type} file: {e}")
        abort(500, description="Internal Server Error")

@app.route('/download_csv')
@login_required
def download_csv():
    logger_id = request.args.get('logger_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not all([logger_id, start_date, end_date]):
        abort(400, description="Missing required parameters")

    df = get_filtered_df(logger_id, start_date, end_date)
    if df is None or df.empty:
        abort(404, description="No data found")

    return send_dataframe_as_file(df, logger_id, start_date, end_date, file_type='csv')

@app.route('/download_excel')
@login_required
def download_excel():
    logger_id = request.args.get('logger_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not all([logger_id, start_date, end_date]):
        abort(400, description="Missing required parameters")

    df = get_filtered_df(logger_id, start_date, end_date)
    if df is None or df.empty:
        abort(404, description="No data found")

    return send_dataframe_as_file(df, logger_id, start_date, end_date, file_type='xlsx')


@app.route('/download_pdf')
@login_required
def download_pdf():
    logger_id = request.args.get('logger_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if not all([logger_id, start_date, end_date]):
        abort(400, description="Missing required parameters")

    df = get_filtered_df(logger_id, start_date, end_date)
    if df is None or df.empty:
        abort(404, description="No data found")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=8)

    page_width = pdf.w - 2 * pdf.l_margin
    col_width = page_width / len(df.columns)
    line_height = pdf.font_size * 2.5

    # Header
    for col in df.columns:
        pdf.cell(col_width, line_height, str(col), border=1, align='C')
    pdf.ln(line_height)

    # Rows (limit to 40 rows for PDF)
    for _, row in df.head(40).iterrows():
        for item in row:
            text = str(item)
            if len(text) > 15:
                text = text[:12] + '...'
            pdf.cell(col_width, line_height, text, border=1)
        pdf.ln(line_height)

    pdf_output = pdf.output(dest='S').encode('latin1')
    output = BytesIO(pdf_output)
    output.seek(0)

    return send_file(output, mimetype='application/pdf', as_attachment=True,
                     download_name=f"{logger_id}_{start_date}_to_{end_date}.pdf")

if __name__ == '__main__':
    app.run(debug=True)
