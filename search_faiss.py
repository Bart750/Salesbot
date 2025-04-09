# ✅ Ultimate SalesBOT Script – Patched Boot-Safe (Sorting removed)
from flask import Flask, request, jsonify
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF
import docx
import os
import signal
import sys
import subprocess
import time
import json
import hashlib
import tempfile
import gc
import psutil
import threading
from datetime import datetime

app = Flask(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]
model = SentenceTransformer('all-MiniLM-L6-v2')
index = None
knowledge_base = {}
file_hashes = set()
processed_files_path = "processed_files.json"
processed_files = set()
processing_status = {
    "running": False,
    "last_run": None,
    "log": {},
    "stage": "idle",
    "memory": 0,
    "boot_triggered": False
}

if os.path.exists(processed_files_path):
    with open(processed_files_path, "r") as f:
        processed_files = set(json.load(f))

EXTENSION_MAP = {
    ".pdf": "PDFs",
    ".txt": "Word_Documents",
    ".docx": "Word_Documents",
    ".csv": "Excel_Files",
    ".xlsx": "Excel_Files",
    ".pptx": "PowerPoints",
    ".py": "Code_Files",
    ".ipynb": "Code_Files",
    ".js": "Code_Files",
    ".json": "Code_Files"
}

BASE_FOLDERS = set(["Word_Documents", "PDFs", "Excel_Files", "PowerPoints", "Code_Files", "Miscellaneous", "SalesBOT_Core_Files"])

def kill_existing_processes():
    subprocess.run(["pkill", "-f", "gunicorn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "waitress"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

def rebuild_faiss():
    global index
    if not knowledge_base:
        return
    embeddings = [model.encode([t], convert_to_numpy=True)[0].astype("float32") for t in knowledge_base.values()]
    index = faiss.IndexFlatL2(len(embeddings[0]))
    index.add(np.array(embeddings))
    faiss.write_index(index, "ai_search_index.faiss")
    gc.collect()

def extract_text(path, ext):
    if ext == ".pdf":
        return " ".join([page.get_text() for page in fitz.open(path)])
    elif ext == ".docx":
        return " ".join([p.text for p in docx.Document(path).paragraphs])
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""

def is_duplicate(content, filename):
    h = hashlib.md5(content.encode("utf-8")).hexdigest()
    return h in file_hashes or filename in processed_files

def log_memory():
    mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    processing_status['memory'] = round(mem, 2)
    return mem

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "SalesBOT is live", "sorted": len(knowledge_base)})

@app.route("/mem", methods=["GET"])
def memory_status():
    return jsonify({"memory_MB": processing_status.get("memory", 0)})

@app.route("/status", methods=["GET"])
def status():
    return jsonify(processing_status)

@app.route("/process_drive", methods=["POST"])
def process_drive():
    return jsonify({"message": "Drive processing is not handled in this script."}), 501

@app.route("/query")
def query():
    question = request.args.get("question")
    if not question:
        return jsonify({"error": "No question provided."}), 400
    if index is None or not knowledge_base:
        return jsonify({"error": "Search system not ready. Try again shortly."}), 503
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
        return jsonify({"error": f"Query failed: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    print(f"\n\n🚀 Booting SalesBOT on port {port}\n")
    kill_existing_processes()
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
