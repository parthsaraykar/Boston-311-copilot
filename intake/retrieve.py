"""Narrow the category cards to the 10 most likely: multilingual embeddings + TF-IDF, cosine search."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from intake.catalog import card_text, cards

ROOT = Path(__file__).resolve().parents[1]
EMBED_MODEL = os.getenv("EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
CACHE = ROOT / "intake" / "card_embeddings.npy"


@lru_cache(maxsize=1)
def _encoder():
    if os.getenv("EMBEDDINGS_DISABLED") == "1":
        return None
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(EMBED_MODEL)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _card_matrix():
    texts = [card_text(c) for c in cards()]
    enc = _encoder()
    emb = None
    if enc is not None:
        if CACHE.exists():
            emb = np.load(CACHE)
            if emb.shape[0] != len(texts):
                emb = None
        if emb is None:
            # embed each phrasing separately and average: closer to how residents actually write
            vecs = []
            for c in cards():
                parts = [f"{c['name']}. {c['description']}"] + c["examples"]
                v = enc.encode(parts, normalize_embeddings=True).mean(axis=0)
                vecs.append(v / np.linalg.norm(v))
            emb = np.vstack(vecs)
            np.save(CACHE, emb)
    tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, analyzer="word")
    tf = tfidf.fit_transform(texts)
    return emb, tfidf, tf


def embed(text: str) -> np.ndarray | None:
    enc = _encoder()
    return None if enc is None else enc.encode([text], normalize_embeddings=True)[0]


def search(text: str, k: int = 10) -> list[dict]:
    """Returns [{card, score, embed_score, tfidf_score}] best first."""
    emb, tfidf, tf = _card_matrix()
    tf_scores = (tf @ tfidf.transform([text]).T).toarray().ravel()
    if emb is not None:
        e_scores = emb @ embed(text)
        scores = 0.8 * e_scores + 0.2 * tf_scores
    else:
        e_scores = np.zeros(len(tf_scores))
        scores = tf_scores
    order = np.argsort(-scores)[:k]
    all_cards = cards()
    return [{"card": all_cards[i], "score": float(scores[i]), "embed_score": float(e_scores[i]),
             "tfidf_score": float(tf_scores[i])} for i in order]


def tfidf_baseline(text: str) -> dict:
    """Baseline for the eval: nearest card by TF-IDF only."""
    _, tfidf, tf = _card_matrix()
    s = (tf @ tfidf.transform([text]).T).toarray().ravel()
    return cards()[int(np.argmax(s))]


def confidence_from_scores(hits: list[dict], temperature: float = 0.03) -> float:
    """Softmax over the top scores: how clearly the best card beats the rest."""
    s = np.array([h["score"] for h in hits])
    if len(s) == 0:
        return 0.0
    p = np.exp((s - s.max()) / temperature)
    p /= p.sum()
    # an absolute floor too: a weak best match shouldn't look confident just because others are weaker
    strength = float(np.clip((s[0] - 0.2) / 0.35, 0, 1))
    return round(float(p[0]) * (0.5 + 0.5 * strength), 3)
