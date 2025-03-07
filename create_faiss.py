import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from googleapiclient.discovery import build
from google.oauth2 import service_account
import fitz  # PyMuPDF for PDFs

# ✅ Path to service account JSON file
SERVICE_ACCOUNT_FILE = "service_account.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# ✅ Authenticate Google Drive using Service Account
def authenticate_drive():
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return creds

# ✅ Initialize AI Model
model = SentenceTransformer('all-MiniLM-L6-v2')
d = model.get_sentence_embedding_dimension()
index = faiss.IndexFlatL2(d)

# ✅ Get Google Drive Files
def get_drive_files():
    creds = authenticate_drive()
    service = build("drive", "v3", credentials=creds)
    results = service.files().list(q="mimeType='application/pdf'", pageSize=10, fields="files(id, name, mimeType)").execute()
    return results.get("files", [])

# ✅ Extract text from a PDF file
def extract_text_from_pdf(file_path):
    text = ""
    with fitz.open(file_path) as doc:
        for page in doc:
            text += page.get_text("text") + "\n"
    return text.strip()

# ✅ Download and Process Drive Files
file_metadata = []
file_embeddings = []
service = build("drive", "v3", credentials=authenticate_drive())

download_folder = "downloads"
os.makedirs(download_folder, exist_ok=True)

for file in get_drive_files():
    file_id = file["id"]
    file_name = file["name"]
    local_path = os.path.join(download_folder, file_name)

    print(f"📥 Streaming {file_name} from Google Drive...")
    request = service.files().get_media(fileId=file_id)
    with open(local_path, "wb") as f:
        f.write(request.execute())

    text = extract_text_from_pdf(local_path)
    if text:
        file_metadata.append(f"{file_name} | {file_id}")  # Store both filename and file ID
        text_embedding = model.encode([text], convert_to_numpy=True)
        file_embeddings.append(text_embedding)
    else:
        print(f"⚠️ No text found in {file_name}")

# ✅ Handle empty file_embeddings case
if not file_embeddings:
    print("⚠️ No files were processed or embeddings could not be generated. Exiting.")
    exit()

# ✅ Convert to FAISS format
file_embeddings = np.vstack(file_embeddings).astype("float32")
index.add(file_embeddings)

# ✅ Save FAISS index and metadata
faiss.write_index(index, "ai_search_index.faiss")
np.save("ai_metadata.npy", np.array(file_metadata, dtype=object))

print(f"✅ FAISS index rebuilt with {len(file_metadata)} Google Drive files!")