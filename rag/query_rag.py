import faiss
import json
import numpy as np
import os
import re
from pathlib import Path
from sentence_transformers import SentenceTransformer

# ✅ Gemini new SDK
# =========================
# 📦 LOAD DATA
# =========================
RAG_DIR = Path(__file__).resolve().parent
index = faiss.read_index(str(RAG_DIR / "faiss_index.index"))

with open(RAG_DIR / "documents.json", "r", encoding="utf-8") as f:
    documents = json.load(f)

model = SentenceTransformer('all-MiniLM-L6-v2')


# =========================
# 🔍 SEARCH FUNCTION (RAG)
# =========================
def search(query, k=10):
    query_lower = query.lower()

    # 🔥 detect intent
    intent = "general"
    if any(word in query_lower for word in ["disease", "yellow", "spots", "infection"]):
        intent = "disease"
    elif "fertilizer" in query_lower:
        intent = "fertilizer"
    elif "soil" in query_lower:
        intent = "soil"

    # embedding
    query_embedding = model.encode([query])
    query_embedding = np.array(query_embedding).astype("float32")

    distances, indices = index.search(query_embedding, k * 5)

    candidates = []
    query_terms = set(re.findall(r"[a-z0-9]+", query_lower))

    for position, i in enumerate(indices[0]):
        doc = documents[i]

        # 🔥 strict filtering
        if intent == "disease" and "type: disease" not in doc:
            continue
        if intent == "fertilizer" and "type: fertilizer" not in doc:
            continue
        if intent == "soil" and "type: soil" not in doc:
            continue

        # 🔥 crop-aware filtering (IMPORTANT)
        if "rice" in query_lower and "crop: rice" not in doc:
            continue
        if "tomato" in query_lower and "crop: tomato" not in doc:
            continue

        doc_lower = doc.lower()
        doc_terms = set(re.findall(r"[a-z0-9]+", doc_lower))
        keyword_overlap = len(query_terms & doc_terms)
        crop_boost = 2 if "rice" in query_terms and "rice" in doc_lower else 0
        candidates.append((keyword_overlap + crop_boost, position, doc))

    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
    return [doc for _, _, doc in candidates[:k]]


# =========================
# 🤖 LLM GENERATION
# =========================
def llm_generate(query, context_docs):
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=api_key)
    context = "\n".join(context_docs)

    # 🔥 STRICT RAG PROMPT
    prompt = f"""
You are an agricultural assistant.

STRICT RULES:
- Use ONLY the given context
- Do NOT use your own knowledge
- If answer is not in context, say "Not enough data"

Context:
{context}

Question:
{query}

Give a simple answer for farmers:
"""

    response = client.models.generate_content(
        model="gemini-3.8-flash",   # ✅ latest working
        contents=prompt
    )

    return response.text


# =========================
# 🚀 FULL PIPELINE
# =========================
def rag_pipeline(query):
    docs = search(query)

    if not docs:
        return "No relevant data found in database."

    answer = llm_generate(query, docs)
    return answer


# =========================
# 🧪 TEST
# =========================
if __name__ == "__main__":
    query = input("Enter your question: ")

    print("\n🔍 Searching...\n")

    result = rag_pipeline(query)

    print("\n🤖 AI Answer:\n")
    print(result)