# drive_utils.py
import os
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)

def fetch_csv_from_drive(logger_id):
    filename = f"{logger_id}_enriched.csv"
    service = get_drive_service()
    query = (
        f"name = '{filename}' and '{FOLDER_ID}' in parents "
        "and mimeType = 'text/csv'"
    )
    res = service.files().list(q=query, fields="files(id, name)", pageSize=1).execute()
    files = res.get('files', [])
    if not files:
        return None

    file_id = files[0]['id']
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh
