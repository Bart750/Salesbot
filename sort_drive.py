# ✅ sort_drive.py – Enhanced Drive Sorting Logic with Quarantine + Scoped Folder Access (with deep recursive fix)
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import tempfile
import hashlib
import os
import json
import numpy as np
from datetime import datetime
from shared import (
    model, knowledge_base, index, rebuild_faiss, extract_text,
    is_duplicate, log_memory, file_hashes, processed_files_path,
    processed_files, EXTENSION_MAP, BASE_FOLDERS, processing_status
)

SCOPES = ["https://www.googleapis.com/auth/drive"]
SALESBOT_FOLDER_NAME = "SalesBOT"

def authenticate_drive():
    try:
        json_data = os.getenv("SERVICE_ACCOUNT_JSON")
        if json_data:
            creds = service_account.Credentials.from_service_account_info(json.loads(json_data), scopes=SCOPES)
        else:
            creds = service_account.Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
        return creds
    except Exception as e:
        processing_status["stage"] = f"Auth error: {e}"
        return None

def find_folder_id(service, folder_name):
    results = service.files().list(q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'",
                                   fields="files(id, name)").execute()
    folders = results.get("files", [])
    return folders[0]['id'] if folders else None

def ensure_folder(service, name):
    results = service.files().list(q=f"mimeType='application/vnd.google-apps.folder' and name='{name}'",
                                   spaces='drive', fields="files(id, name)").execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]['id']
    folder_metadata = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
    folder = service.files().create(body=folder_metadata, fields='id').execute()
    return folder['id']

def move_file(service, file_id, new_folder_id, move_log):
    try:
        file = service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))
        service.files().update(fileId=file_id, addParents=new_folder_id, removeParents=previous_parents, fields='id, parents').execute()
        move_log.append(file_id)
        return True
    except Exception as e:
        processing_status['log'].setdefault("move_errors", []).append({"file_id": file_id, "error": str(e)})
        return False

def get_all_files_iteratively(service, root_folder_id):
    stack = [root_folder_id]
    all_files, folders = [], []

    while stack:
        current = stack.pop()
        page_token = None
        while True:
            try:
                response = service.files().list(
                    q=f"'{current}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, size)",
                    pageToken=page_token
                ).execute()

                for item in response.get("files", []):
                    if item["mimeType"] == "application/vnd.google-apps.folder":
                        folders.append((item["id"], item["name"]))
                        stack.append(item["id"])
                    else:
                        all_files.append(item)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            except Exception as e:
                processing_status["log"].setdefault("folder_scan_errors", []).append({"folder_id": current, "error": str(e)})
                break

    processing_status["log"]["folders_found"] = [f[1] for f in folders]
    return all_files, folders

def run_drive_processing():
    global index
    processing_status.update({"running": True, "stage": "Starting cleanup", "log": {}})
    move_log, error_log = {}, []

    try:
        creds = authenticate_drive()
        if not creds:
            processing_status.update({"running": False, "stage": "Drive authentication failed"})
            return

        service = build("drive", "v3", credentials=creds)
        root_id = find_folder_id(service, SALESBOT_FOLDER_NAME)
        if not root_id:
            processing_status.update({"running": False, "stage": "SalesBOT folder not found"})
            return

        processing_status["stage"] = f"Scanning '{SALESBOT_FOLDER_NAME}'"
        files, folders = get_all_files_iteratively(service, root_id)

        ext_counter = {}
        for f in files:
            ext = os.path.splitext(f['name'])[-1].lower()
            ext_counter[ext] = ext_counter.get(ext, 0) + 1

        folder_ids = {name: ensure_folder(service, name) for name in BASE_FOLDERS}
        quarantine_id = ensure_folder(service, "Quarantine")

        new_knowledge = {}
        for file in files:
            try:
                name, file_id = file['name'], file['id']
                ext = os.path.splitext(name)[-1].lower()
                if not ext:
                    ext = ".unknown"
                size = int(file.get("size", 0))

                if size > 50 * 1024 * 1024:
                    move_file(service, file_id, quarantine_id, move_log.setdefault("Quarantine", []))
                    error_log.append({"file": name, "reason": "File too large"})
                    continue

                request = service.files().get_media(fileId=file_id)
                path = os.path.join(tempfile.gettempdir(), name)
                with open(path, "wb") as f:
                    downloader = MediaIoBaseDownload(f, request)
                    done, retries = False, 0
                    while not done and retries < 20:
                        _, done = downloader.next_chunk()
                        retries += 1

                text = extract_text(path, ext)
                os.remove(path)

                if not text or len(text.strip()) < 10:
                    move_file(service, file_id, quarantine_id, move_log.setdefault("Quarantine", []))
                    error_log.append({"file": name, "reason": "Empty or unreadable content"})
                    continue

                category = EXTENSION_MAP.get(ext, "Miscellaneous") if ext_counter.get(ext, 0) >= 10 else "Miscellaneous"

                if not is_duplicate(text, name):
                    if category == "Word_Documents":
                        new_knowledge[name] = text
                        file_hashes.add(hashlib.md5(text.encode("utf-8")).hexdigest())
                        processed_files.add(name)

                move_file(service, file_id, folder_ids[category], move_log.setdefault(category, []))
                log_memory()

            except Exception as e:
                move_file(service, file['id'], quarantine_id, move_log.setdefault("Quarantine", []))
                error_log.append({"file": file.get('name'), "reason": str(e)})

        processing_status["stage"] = "Cleaning folders"
        for fid, name in folders:
            if name in BASE_FOLDERS:
                continue
            contents = service.files().list(q=f"'{fid}' in parents", fields="files(id)").execute().get("files", [])
            if not contents:
                try:
                    service.files().delete(fileId=fid).execute()
                except Exception as e:
                    error_log.append({"folder": name, "reason": str(e)})

        knowledge_base.update(new_knowledge)
        np.save("ai_metadata.npy", knowledge_base)
        with open(processed_files_path, "w") as f:
            json.dump(list(processed_files), f)

        if new_knowledge:
            rebuild_faiss()

    except Exception as e:
        error_log.append({"fatal": str(e)})
        processing_status["stage"] = f"Fatal error: {e}"

    finally:
        processing_status.update({
            "running": False,
            "last_run": datetime.utcnow().isoformat(),
            "stage": "idle",
            "log": {
                "moved": move_log,
                "errors": error_log,
                "count": len(files),
                "processed": sum(len(v) for v in move_log.values()),
                "duplicates_skipped": len(processed_files),
            }
        })
