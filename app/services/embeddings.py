import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.15


def is_similar(text: str, prompt: str) -> bool:
    vectorizer = TfidfVectorizer()
    try:
        tfidf = vectorizer.fit_transform([text, prompt])
        score = cosine_similarity(tfidf[0], tfidf[1])[0][0]
        logger.debug(f"[TFIDF] similarity={score:.3f} (threshold={SIMILARITY_THRESHOLD})")
        return float(score) >= SIMILARITY_THRESHOLD
    except Exception as e:
        logger.error(f"[TFIDF] error: {e}")
        return True