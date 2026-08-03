import os
import re
from typing import List, Optional, Any


class DocumentLike:
    def __init__(self, page_content: str, metadata: Optional[dict] = None):
        self.page_content = page_content
        self.metadata = metadata or {}


try:
    from langchain_core.documents import Document as LangchainDocument
except Exception:  # pragma: no cover - fallback for lightweight test environments
    LangchainDocument = DocumentLike


def _normalize_whitespace(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    text = re.sub(r"(?i)\bpage\s*\d+\b", "", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _is_meaningful_chunk(content: str, *, min_length: int = 80) -> bool:
    if not content:
        return False
    cleaned = re.sub(r"\s+", " ", content).strip()
    if len(cleaned) < min_length:
        return False
    if re.fullmatch(r"[\W_]+", cleaned):
        return False
    return True


def preprocess_pages(pages: List[Any]) -> List[Any]:
    documents = []
    for idx, page in enumerate(pages):
        raw_text = getattr(page, "page_content", "") or ""
        cleaned_text = _normalize_whitespace(raw_text)
        if not cleaned_text:
            continue

        metadata = dict(getattr(page, "metadata", {}) or {})
        metadata.setdefault("page", idx + 1)
        metadata.setdefault("source_file", os.path.basename(str(metadata.get("source", "unknown.pdf"))))
        metadata.setdefault("page_number", int(metadata.get("page", idx + 1)))

        documents.append(LangchainDocument(page_content=cleaned_text, metadata=metadata))

    return documents


def build_chunks_from_pages(
    pages: List[Any],
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    separators: Optional[List[str]] = None,
) -> List[Any]:
    documents = preprocess_pages(pages)
    if not documents:
        return []

    if separators is None:
        separators = ["\n\n", "\n", " ", ""]

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
        )
        chunks = splitter.split_documents(documents)
    except Exception:
        chunks = []
        for doc in documents:
            content = doc.page_content
            parts = re.split(r"\n{2,}", content)
            for part in parts:
                if part.strip():
                    chunks.append(LangchainDocument(page_content=part.strip(), metadata=doc.metadata.copy()))

    cleaned_chunks: List[Any] = []
    seen_signatures = set()

    for idx, chunk in enumerate(chunks):
        content = _normalize_whitespace(getattr(chunk, "page_content", "") or "")
        if not _is_meaningful_chunk(content, min_length=80):
            continue

        metadata = dict(getattr(chunk, "metadata", {}) or {})
        metadata.update({
            "chunk_id": idx,
            "char_count": len(content),
            "section_heading": content.splitlines()[0][:80] if content.splitlines() else content[:80],
            "source_file": metadata.get("source_file", "unknown.pdf"),
            "page_number": metadata.get("page_number", metadata.get("page", 1)),
        })

        signature = re.sub(r"\s+", " ", content)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        cleaned_chunks.append(LangchainDocument(page_content=content, metadata=metadata))

    return cleaned_chunks


def get_embedding_model():
    from langchain_community.embeddings import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name="jhgan/ko-sroberta-multitask",
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


def get_reranker_model():
    from sentence_transformers import CrossEncoder

    return CrossEncoder("BAAI/bge-reranker-v2-m3")


def build_vector_store_from_file(file_path: str, output_dir: str, *, doc_id: int, chunk_size: int = 800, chunk_overlap: int = 120):
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_community.vectorstores import FAISS

    loader = PyPDFLoader(file_path)
    pages = loader.load()
    chunks = build_chunks_from_pages(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if not chunks:
        raise ValueError("No chunks were generated from the uploaded PDF")

    embeddings = get_embedding_model()
    vector_db = FAISS.from_documents(chunks, embeddings)

    os.makedirs(output_dir, exist_ok=True)
    vector_db.save_local(output_dir)
    return len(chunks)


def load_vector_store(vector_path: str, embedding_model):
    from langchain_community.vectorstores import FAISS

    return FAISS.load_local(
        vector_path,
        embedding_model,
        allow_dangerous_deserialization=True,
    )


def search_across_vector_stores(
    query: str,
    vector_root: str,
    embedding_model,
    reranker_model,
    *,
    top_k: int = 5,
    initial_candidates: int = 20,
):
    candidates = []

    for doc_id in sorted(os.listdir(vector_root)):
        doc_path = os.path.join(vector_root, doc_id)
        if not os.path.isdir(doc_path):
            continue

        try:
            vector_db = load_vector_store(doc_path, embedding_model)
            docs = vector_db.similarity_search_with_score(query, k=3)
        except Exception:
            continue

        for doc, score in docs:
            candidates.append({
                "doc_id": doc_id,
                "content": getattr(doc, "page_content", ""),
                "metadata": getattr(doc, "metadata", {}),
                "score": float(score),
            })

    if not candidates:
        return []

    candidates = sorted(candidates, key=lambda item: item["score"])[:initial_candidates]

    pairs = [(query, item["content"]) for item in candidates]
    rerank_scores = reranker_model.predict(pairs)

    reranked = sorted(
        zip(candidates, rerank_scores),
        key=lambda item: item[1],
        reverse=True,
    )

    results = []
    for candidate, _ in reranked[:top_k]:
        metadata = dict(candidate.get("metadata", {}) or {})
        metadata.setdefault("doc_id", candidate.get("doc_id"))
        metadata.setdefault("source_file", metadata.get("source_file", "unknown.pdf"))
        results.append({
            "doc_id": candidate["doc_id"],
            "content": candidate["content"],
            "metadata": metadata,
            "score": round(float(candidate["score"]), 4),
        })

    return results
