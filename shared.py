# ✅ shared.py – Runtime State, Safe Indexing, File Deduplication
import faiss
import numpy as np
import hashlib
import json
import os
import gc
import psutil
from sentence_transformers import SentenceTransformer
import fitz  # PyMuPDF
import docx

# 🔧 Runtime status
processing_status = {
    "running": False,
    "last_run": None,
    "log": {},
    "stage": "idle",
    "memory": 0,
    "boot_triggered": False
}

# 🧠 Embedding engine
model = SentenceTransformer('all-MiniLM-L6-v2')
index = None
knowledge_base = {}
file_hashes = set()

# ✅ Load prior processed files
processed_files_path = "processed_files.json"
processed_files = set()
if os.path.exists(processed_files_path):
    try:
        with open(processed_files_path, "r") as f:
            processed_files = set(json.load(f))
    except Exception as e:
        processing_status["stage"] = f"Failed to load processed_files.json: {e}"
        processed_files = set()

# ✅ Load vector knowledge base
if os.path.exists("ai_metadata.npy"):
    try:
        kb = np.load("ai_metadata.npy", allow_pickle=True).item()
        if isinstance(kb, dict):
            knowledge_base.update(kb)
        else:
            raise ValueError("ai_metadata.npy did not contain a dictionary")
    except Exception as e:
        processing_status["stage"] = f"Metadata load failed: {e}"
        knowledge_base = {}

# 📁 Extension routing
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
    ".json": "Code_Files",
    ".zip": "System_Files",
    ".exe": "System_Files",
    ".dmg": "System_Files",
    ".md": "Word_Documents",
    ".html": "Word_Documents"
}

# 📂 Folder categories
BASE_FOLDERS = set([
    "Word_Documents", "PDFs", "Excel_Files", "PowerPoints",
    "Code_Files", "Miscellaneous", "SalesBOT_Core_Files",
    "System_Files", "Quarantine"
])

# 🔁 FAISS index rebuild
def rebuild_faiss():
    global index
    try:
        valid_texts = [v for v in knowledge_base.values() if isinstance(v, str) and v.strip()]
        if not valid_texts:
            processing_status["stage"] = "FAISS rebuild skipped (no valid text entries)"
            return
        embeddings = [
            model.encode([t], convert_to_numpy=True)[0].astype("float32")
            for t in valid_texts
        ]
        dim = len(embeddings[0])
        index = faiss.IndexFlatL2(dim)
        index.add(np.array(embeddings))
        faiss.write_index(index, "ai_search_index.faiss")
        processing_status["stage"] = f"FAISS rebuilt with {len(embeddings)} entries"
    except Exception as e:
        processing_status["stage"] = f"FAISS rebuild failed: {e}"
    finally:
        gc.collect()

# 📜 Extract readable content
def extract_text(path, ext):
    try:
        if ext == ".pdf":
            return " ".join([page.get_text() for page in fitz.open(path)])
        elif ext == ".docx":
            return " ".join([p.text for p in docx.Document(path).paragraphs])
        elif ext in [".txt", ".md", ".html"]:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif ext == ".csv":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception:
        return ""
    return ""

# 🔐 Duplication check
def is_duplicate(content, filename):
    h = hashlib.md5(content.encode("utf-8")).hexdigest()
    return h in file_hashes or filename in processed_files

# 🧠 Memory logging
def log_memory():
    mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    processing_status["memory"] = round(mem, 2)
    return processing_status["memory"]
