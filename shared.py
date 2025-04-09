# ✅ shared.py – Central Shared State & Utility Functions
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

# 🔧 Shared runtime status (imported by sort_drive and search_faiss)
processing_status = {
    "running": False,
    "last_run": None,
    "log": {},
    "stage": "idle",
    "memory": 0,
    "boot_triggered": False
}

# 🧠 Load embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')
index = None
knowledge_base = {}
file_hashes = set()

# 🗂️ Load previously processed file names
processed_files_path = "processed_files.json"
processed_files = set()
if os.path.exists(processed_files_path):
    with open(processed_files_path, "r") as f:
        processed_files = set(json.load(f))

# 🗃️ Categorization map for file extensions
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
    ".dmg": "System_Files"
}

BASE_FOLDERS = set([
    "Word_Documents", "PDFs", "Excel_Files", "PowerPoints",
    "Code_Files", "Miscellaneous", "SalesBOT_Core_Files", "System_Files"
])

# 🔁 FAISS index rebuild
def rebuild_faiss():
    global index
    if not knowledge_base:
        return
    embeddings = [model.encode([t], convert_to_numpy=True)[0].astype("float32") for t in knowledge_base.values()]
    index = faiss.IndexFlatL2(len(embeddings[0]))
    index.add(np.array(embeddings))
    faiss.write_index(index, "ai_search_index.faiss")
    gc.collect()

# 🧾 File content extractor
def extract_text(path, ext):
    if ext == ".pdf":
        return " ".join([page.get_text() for page in fitz.open(path)])
    elif ext == ".docx":
        return " ".join([p.text for p in docx.Document(path).paragraphs])
    elif ext == ".txt":
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""

# 🧯 Duplicate check
def is_duplicate(content, filename):
    h = hashlib.md5(content.encode("utf-8")).hexdigest()
    return h in file_hashes or filename in processed_files

# 🧠 Memory log
def log_memory():
    mem = psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024
    processing_status["memory"] = round(mem, 2)
    return round(mem, 2)
