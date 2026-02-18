import os
import io
import re
import json
import base64
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Google Drive API scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Root folder ID from shared link
ROOT_FOLDER_ID = '1MbMlTE0jKnZlxCL0sW1eY4umETOfcx9M'

# Credentials paths
CREDENTIALS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE_ACCOUNT_FILE = os.path.join(CREDENTIALS_DIR, 'service-account.json')
OAUTH_CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, 'oauth-credentials.json')
OAUTH_TOKEN_FILE = os.path.join(CREDENTIALS_DIR, 'oauth-token.json')

# Environment variable alternatives
SERVICE_ACCOUNT_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
GOOGLE_OAUTH_CREDENTIALS = os.environ.get('GOOGLE_OAUTH_CREDENTIALS')
GOOGLE_OAUTH_TOKEN = os.environ.get('GOOGLE_OAUTH_TOKEN')


def get_drive_service():
    """Get authenticated Google Drive service.

    Priority:
    1. OAuth2 user credentials (works with regular Google Drive)
    2. Service account (requires Shared Drive or domain-wide delegation)
    """

    # Try OAuth2 first (works with regular Drive)
    if GOOGLE_OAUTH_TOKEN or os.path.exists(OAUTH_TOKEN_FILE):
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            if GOOGLE_OAUTH_TOKEN:
                # Try to decode as base64 first, fall back to raw JSON
                try:
                    decoded = base64.b64decode(GOOGLE_OAUTH_TOKEN).decode('utf-8')
                    token_info = json.loads(decoded)
                except Exception:
                    # Not base64, try parsing as raw JSON
                    token_info = json.loads(GOOGLE_OAUTH_TOKEN)
            else:
                with open(OAUTH_TOKEN_FILE, 'r') as f:
                    token_info = json.load(f)

            credentials = Credentials.from_authorized_user_info(token_info, SCOPES)

            # Refresh if expired
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                # Save refreshed token
                if not GOOGLE_OAUTH_TOKEN and os.path.exists(OAUTH_TOKEN_FILE):
                    with open(OAUTH_TOKEN_FILE, 'w') as f:
                        f.write(credentials.to_json())

            return build('drive', 'v3', credentials=credentials)
        except Exception as e:
            print(f"OAuth2 failed: {e}, falling back to service account")

    # Fall back to service account
    from google.oauth2 import service_account as sa

    if SERVICE_ACCOUNT_JSON:
        service_account_info = json.loads(SERVICE_ACCOUNT_JSON)
        credentials = sa.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
    elif os.path.exists(SERVICE_ACCOUNT_FILE):
        credentials = sa.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
    else:
        raise FileNotFoundError(
            f"Google Drive credentials not found.\n"
            f"Either:\n"
            f"1. Set up OAuth2: place oauth-credentials.json and run the auth flow\n"
            f"2. Use service account: place service-account.json or set GOOGLE_SERVICE_ACCOUNT_JSON\n\n"
            f"For OAuth2 setup, run: python -c 'from app.drive_service import setup_oauth; setup_oauth()'"
        )

    return build('drive', 'v3', credentials=credentials)


def setup_oauth():
    """Interactive OAuth2 setup for regular Google Drive access."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not os.path.exists(OAUTH_CREDENTIALS_FILE) and not GOOGLE_OAUTH_CREDENTIALS:
        print("OAuth credentials not found!")
        print(f"Please download OAuth 2.0 Client ID credentials from Google Cloud Console")
        print(f"and save as: {OAUTH_CREDENTIALS_FILE}")
        print("\nSteps:")
        print("1. Go to Google Cloud Console -> APIs & Services -> Credentials")
        print("2. Create OAuth 2.0 Client ID (Desktop application)")
        print("3. Download JSON and save as oauth-credentials.json")
        return

    if GOOGLE_OAUTH_CREDENTIALS:
        creds_info = json.loads(GOOGLE_OAUTH_CREDENTIALS)
        flow = InstalledAppFlow.from_client_config(creds_info, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CREDENTIALS_FILE, SCOPES)

    credentials = flow.run_local_server(port=0)

    # Save the token
    with open(OAUTH_TOKEN_FILE, 'w') as f:
        f.write(credentials.to_json())

    print(f"OAuth token saved to: {OAUTH_TOKEN_FILE}")
    print("Google Drive is now authenticated!")


def find_or_create_folder(service, folder_name: str, parent_id: str, supports_all_drives: bool = True) -> str:
    """Find existing folder or create new one. Returns folder ID."""
    # Search for existing folder
    query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(
        q=query,
        fields="files(id, name)",
        supportsAllDrives=supports_all_drives,
        includeItemsFromAllDrives=supports_all_drives
    ).execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']

    # Create new folder
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(
        body=file_metadata,
        fields='id',
        supportsAllDrives=supports_all_drives
    ).execute()
    return folder['id']


def upload_invoice_to_drive(
    file_bytes: bytes,
    filename: str,
    invoice_date: str,
    company: str,
    invoice_number: str,
    mime_type: str = 'application/pdf'
) -> str:
    """
    Upload invoice to Google Drive organized by Year/Month/Company/InvoiceNo.
    Returns the file's web view link.

    Structure: Root Folder / Year / Month / Company / InvoiceNo / filename
    """
    service = get_drive_service()

    # Extract year and month from invoice date
    try:
        date_obj = datetime.strptime(invoice_date, '%Y-%m-%d')
        year = str(date_obj.year)
        month = f"{date_obj.month:02d}"  # Zero-padded month (01-12)
    except (ValueError, TypeError):
        now = datetime.now()
        year = str(now.year)
        month = f"{now.month:02d}"

    # Clean company name for folder (remove special characters)
    clean_company = ''.join(c for c in company if c.isalnum() or c in ' -_').strip()
    if not clean_company:
        clean_company = 'Unknown Company'

    # Clean invoice number for folder (remove special characters that aren't allowed in folder names)
    clean_invoice_no = ''.join(c for c in invoice_number if c.isalnum() or c in ' -_').strip()
    if not clean_invoice_no:
        clean_invoice_no = 'Unknown Invoice'

    # Create folder structure: Root / Year / Month / Company / InvoiceNo
    year_folder_id = find_or_create_folder(service, year, ROOT_FOLDER_ID)
    month_folder_id = find_or_create_folder(service, month, year_folder_id)
    company_folder_id = find_or_create_folder(service, clean_company, month_folder_id)
    invoice_folder_id = find_or_create_folder(service, clean_invoice_no, company_folder_id)

    # Upload the file
    file_metadata = {
        'name': filename,
        'parents': [invoice_folder_id]
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=mime_type,
        resumable=True
    )

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink',
        supportsAllDrives=True
    ).execute()

    return file.get('webViewLink', f"https://drive.google.com/file/d/{file['id']}/view")


def check_drive_auth() -> bool:
    """Check if Google Drive is authenticated."""
    try:
        service = get_drive_service()
        # Try to list files to verify access
        service.files().list(pageSize=1).execute()
        return True
    except Exception:
        return False


def list_folder_contents(folder_id: str = ROOT_FOLDER_ID) -> list:
    """List contents of a folder (for debugging)."""
    service = get_drive_service()
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
    return results.get('files', [])


def extract_file_id_from_link(drive_link: str) -> str | None:
    """Extract Google Drive file ID from a web view link.

    Supports formats like:
    - https://drive.google.com/file/d/{FILE_ID}/view
    - https://drive.google.com/open?id={FILE_ID}
    """
    if not drive_link:
        return None

    # Pattern for /file/d/{id}/view format
    match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', drive_link)
    if match:
        return match.group(1)

    # Pattern for ?id={id} format
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', drive_link)
    if match:
        return match.group(1)

    return None


def delete_file_from_drive(drive_link: str) -> bool:
    """Delete a file from Google Drive using its web view link.

    Returns True if file was deleted, False if file not found or error occurred.
    """
    file_id = extract_file_id_from_link(drive_link)
    if not file_id:
        print(f"Could not extract file ID from link: {drive_link}")
        return False

    try:
        service = get_drive_service()
        service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        print(f"Deleted file from Drive: {file_id}")
        return True
    except Exception as e:
        print(f"Error deleting file from Drive: {e}")
        return False


def delete_files_from_drive(drive_links: list[str]) -> int:
    """Delete multiple files from Google Drive.

    Returns count of successfully deleted files.
    """
    deleted_count = 0
    for link in drive_links:
        if link and delete_file_from_drive(link):
            deleted_count += 1
    return deleted_count


def get_folder_id_from_file_link(drive_link: str) -> str | None:
    """Get the parent folder ID from a file's Drive link.

    Returns the folder ID or None if not found.
    """
    file_id = extract_file_id_from_link(drive_link)
    if not file_id:
        return None

    try:
        service = get_drive_service()
        file = service.files().get(fileId=file_id, fields='parents', supportsAllDrives=True).execute()
        parents = file.get('parents', [])
        return parents[0] if parents else None
    except Exception as e:
        print(f"Error getting folder ID: {e}")
        return None


def get_folder_link_from_file(drive_link: str) -> str | None:
    """Get the Google Drive folder link from a file's link.

    Returns the folder URL or None if not found.
    """
    folder_id = get_folder_id_from_file_link(drive_link)
    if folder_id:
        return f"https://drive.google.com/drive/folders/{folder_id}"
    return None


def upload_attachment_to_folder(
    file_bytes: bytes,
    filename: str,
    folder_id: str,
    mime_type: str = None
) -> str | None:
    """Upload an attachment file to a specific Google Drive folder.

    Args:
        file_bytes: The file content as bytes
        filename: Name for the file
        folder_id: The Google Drive folder ID to upload to
        mime_type: Optional MIME type (auto-detected if not provided)

    Returns the file's web view link or None on error.
    """
    if not mime_type:
        # Auto-detect mime type based on extension
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        mime_map = {
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'txt': 'text/plain',
        }
        mime_type = mime_map.get(ext, 'application/octet-stream')

    try:
        service = get_drive_service()

        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        return file.get('webViewLink', f"https://drive.google.com/file/d/{file['id']}/view")
    except Exception as e:
        print(f"Error uploading attachment: {e}")
        return None
