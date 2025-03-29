# ✅ Fixed and Cleaned SalesBOT Script
from flask import Flask, request, jsonify
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
import fitz  # PyMuPDF
import os
import signal
import sys
import subprocess
import time
import json
import zipfile
import hashlib
import tempfile
import gc
import psutil
import requests
import threading

app = Flask(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
model = SentenceTransformer('all-MiniLM-L6-v2')
index = None
knowledge_base = {}
file_hashes = set()
processed_files_path = "processed_files.json"
processed_files = set()

if os.path.exists(processed_files_path):
    with open(processed_files_path, "r") as f:
        processed_files = set(json.load(f))

# ✅ Kill existing server processes
def kill_existing_processes():
    subprocess.run(["pkill", "-f", "gunicorn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "waitress"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

# ✅ Authenticate Google Drive

def authenticate_drive():
    try:
        SERVICE_ACCOUNT_JSON = os.getenv("SERVICE_ACCOUNT_JSON")
        if SERVICE_ACCOUNT_JSON:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(SERVICE_ACCOUNT_JSON), scopes=SCOPES)
        else:
            SERVICE_ACCOUNT_FILE = "service_account.json"
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return creds
    except Exception as e:
        print(f"❌ Auth error: {e}")
        return None

# ✅ FAISS Handling

def rebuild_faiss():
    global index
    if not knowledge_base:
        return
    embeddings = [model.encode([text], convert_to_numpy=True)[0].astype("float32") for text in knowledge_base.values()]
    index = faiss.IndexFlatL2(len(embeddings[0]))
    index.add(np.array(embeddings))
    faiss.write_index(index, "ai_search_index.faiss")
    print(f"✅ FAISS rebuilt with {len(embeddings)} entries.")

def load_faiss():
    global index
    try:
        index = faiss.read_index("ai_search_index.faiss")
        index.nprobe = 1
        print("✅ FAISS index loaded.")
    except:
        print("⚠️ No FAISS index found.")
        index = None

def load_knowledge_base():
    global knowledge_base
    try:
        knowledge_base = dict(np.load("ai_metadata.npy", allow_pickle=True).item())
        print(f"✅ Knowledge base loaded with {len(knowledge_base)} entries.")
    except:
        print("⚠️ No existing knowledge base found.")

# ✅ Helper Functions

def is_duplicate(content, filename):
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    if content_hash in file_hashes or filename in processed_files:
        return True
    file_hashes.add(content_hash)
    processed_files.add(filename)
    return False

def log_memory():
    mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    print(f"🔍 RAM: {mem:.2f} MB")

# ✅ Routes
@app.route("/")
def home():
    return jsonify({"status": "OK", "message": "SalesBOT API running."})

@app.route("/health")
def health():
    return jsonify({"status": "Live"})

@app.route("/process_drive", methods=["POST"])
def process_drive():
    creds = authenticate_drive()
    if not creds:
        return jsonify({"error": "Drive authentication failed."}), 500

    service = build("drive", "v3", credentials=creds)
    results = service.files().list(q="name contains '.zip'", fields="files(id, name)").execute()
    files = results.get("files", [])
    limit = int(request.args.get("limit", 3))
    processed, new_knowledge = 0, {}

    for file in files:
        if processed >= limit:
            break
        try:
            file_id, name = file["id"], file["name"]
            request = service.files().get_media(fileId=file_id)
            temp_path = os.path.join(tempfile.gettempdir(), name)
            with open(temp_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            if not zipfile.is_zipfile(temp_path):
                continue

            with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                for zi in zip_ref.infolist():
                    if processed >= limit:
                        break
                    if zi.filename.endswith(".pdf"):
                        with zip_ref.open(zi) as f:
                            doc = fitz.open("pdf", f.read())
                            text = "".join([p.get_text("text") for p in doc[:10]]).strip()
                            doc.close()
                            if text and not is_duplicate(text, zi.filename):
                                new_knowledge[zi.filename] = text
                                processed += 1
                                log_memory()
        except Exception as e:
            print(f"❌ Failed: {file['name']} — {e}")

    knowledge_base.update(new_knowledge)
    np.save("ai_metadata.npy", knowledge_base)
    with open(processed_files_path, "w") as f:
        json.dump(list(processed_files), f)
    rebuild_faiss()
    return jsonify({"message": f"Processed {processed} files.", "files": list(new_knowledge.keys())})

@app.route("/clean_drive_duplicates", methods=["GET", "POST"])
def clean_drive_duplicates():
    creds = authenticate_drive()
    if not creds:
        return jsonify({"error": "Drive auth failed."}), 500
    service = build("drive", "v3", credentials=creds)
    files = service.files().list(q="mimeType='application/zip'", fields="files(id, name)").execute().get("files", [])
    seen, deleted = {}, []

    for file in files:
        try:
            request = service.files().get_media(fileId=file["id"])
            with tempfile.NamedTemporaryFile(delete=False) as tf:
                downloader = MediaIoBaseDownload(tf, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            path = tf.name
            if not zipfile.is_zipfile(path):
                continue

            concat = ""
            with zipfile.ZipFile(path, 'r') as z:
                for zi in z.infolist():
                    if zi.filename.endswith(".pdf"):
                        with z.open(zi) as f:
                            try:
                                doc = fitz.open("pdf", f.read())
                                concat += "".join([p.get_text("text") for p in doc[:5]])
                                doc.close()
                            except:
                                continue

            content_hash = hashlib.md5(concat.encode("utf-8")).hexdigest()
            if content_hash in seen:
                service.files().delete(fileId=file["id"]).execute()
                deleted.append(file["name"])
            else:
                seen[content_hash] = file["name"]
            os.remove(path)
        except Exception as e:
            print(f"❌ File error: {file['name']} — {e}")

    return jsonify({"message": f"Deleted {len(deleted)} duplicates.", "deleted_files": deleted})

@app.route("/query")
def query_knowledge():
    question = request.args.get("question")
    if not question:
        return jsonify({"error": "No question provided."}), 400

    if index is None:
        load_faiss()
    if not knowledge_base:
        load_knowledge_base()
    if index is None:
        return jsonify({"error": "FAISS not available."}), 500

    try:
        query_embedding = model.encode([question], convert_to_numpy=True).astype("float32")
        D, I = index.search(query_embedding, 3)
        keys = list(knowledge_base.keys())
        results = []
        for idx in I[0]:
            if idx == -1 or idx >= len(keys):
                continue
            results.append({"source": keys[idx], "insight": knowledge_base[keys[idx]][:500] + "..."})
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Auto Sync Drive

def auto_sync_drive(interval=10):
    def loop():
        while True:
            print("🔁 Auto-syncing...")
            try:
                with app.test_request_context():
                    process_drive()
                    clean_drive_duplicates()
            except Exception as e:
                print(f"❌ Sync error: {e}")
            time.sleep(interval * 60)

    threading.Thread(target=loop, daemon=True).start()

# ✅ Graceful shutdown
signal.signal(signal.SIGTERM, lambda s, f: sys.exit(0))
signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

# ✅ Start API
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Starting on port {port}")
    if os.system(f"netstat -an | grep {port}") == 0:
        kill_existing_processes()
    load_faiss()
    load_knowledge_base()
    auto_sync_drive()

    from waitress import serve
    try:
        serve(app, host="0.0.0.0", port=port)
    except OSError as e:
        if "Address already in use" in str(e):
            kill_existing_processes()
            os.system(f"gunicorn -w 2 -b 0.0.0.0:{port} search_faiss:app")
        else:
            raise e
