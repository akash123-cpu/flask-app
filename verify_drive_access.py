import os
from io import BytesIO
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv

load_dotenv()

SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')

def download_file(file_id, file_name, mime_type, drive_service, save_path='downloads'):
    os.makedirs(save_path, exist_ok=True)
    fh = BytesIO()

    # Define exportable MIME types
    export_mime_types = {
        'application/vnd.google-apps.document': 'application/pdf',
        'application/vnd.google-apps.spreadsheet': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.google-apps.presentation': 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    }

    extension_map = {
        'application/pdf': '.pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx'
    }

    if mime_type in export_mime_types:
        export_mime = export_mime_types[mime_type]
        file_name += extension_map.get(export_mime, '')
        request = drive_service.files().export_media(fileId=file_id, mimeType=export_mime)
    else:
        request = drive_service.files().get_media(fileId=file_id)

    downloader = MediaIoBaseDownload(fh, request)
    done = False
    print(f"📥 Downloading: {file_name}")
    while not done:
        status, done = downloader.next_chunk()
        if status:
            print(f"   ➤ Progress: {int(status.progress() * 100)}%")

    file_path = os.path.join(save_path, file_name)
    with open(file_path, 'wb') as f:
        f.write(fh.getbuffer())
    print(f"✅ Saved to: {file_path}\n")


def main():
    if not SERVICE_ACCOUNT_FILE or not DRIVE_FOLDER_ID:
        print("❌ Missing environment variables.")
        return

    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/drive.readonly']
    )
    drive_service = build('drive', 'v3', credentials=credentials)

    query = f"'{DRIVE_FOLDER_ID}' in parents and trashed = false"
    results = drive_service.files().list(q=query, pageSize=100, fields="files(id, name, mimeType)").execute()
    files = results.get('files', [])

    if not files:
        print("❌ No files found in the folder.")
        return

    print(f"📂 Files in folder {DRIVE_FOLDER_ID}:\n")
    for i, file in enumerate(files, start=1):
        print(f"{i}. {file['name']} (ID: {file['id']})")

    print("\n⬇️ Starting downloads...\n")

    for file in files:
        try:
            download_file(file['id'], file['name'], file['mimeType'], drive_service)
        except Exception as e:
            print(f"❌ Failed to download {file['name']}: {e}")

if __name__ == "__main__":
    main()
