import json
import faiss
import numpy as np
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

# load cleaned data
with open("data/processed_docs.json", "r") as f:
    documents = json.load(f)

print(f"Total documents: {len(documents)}")

# load embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

# FAISS setup
dimension = 384  # for MiniLM model
index = faiss.IndexFlatL2(dimension)

batch_size = 1000

# process in batches
for i in tqdm(range(0, len(documents), batch_size)):
    batch = documents[i:i+batch_size]
    
    embeddings = model.encode(batch)
    embeddings = np.array(embeddings).astype("float32")
    
    index.add(embeddings)

# save index
faiss.write_index(index, "rag/faiss_index.index")

# save documents (same order)
with open("rag/documents.json", "w") as f:
    json.dump(documents, f)

print("FAISS index built successfully ✅")