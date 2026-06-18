import logging
from collections.abc import Sequence
from dataclasses import dataclass

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KeywordSearchResult:
    text: str
    score: float
    metadata: dict


class KeywordSearchEngine:
    """BM25 关键词检索引擎，内存缓存，按知识库分索引。"""

    def __init__(self) -> None:
        self._indexes: dict[str, "BM25OkapiWrapper"] = {}

    def build_index(
        self,
        collection_name: str,
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        from rank_bm25 import BM25Okapi

        tokenized = [_tokenize(text) for text in texts]
        self._indexes[collection_name] = BM25OkapiWrapper(
            bm25=BM25Okapi(tokenized),
            texts=texts,
            metadatas=metadatas,
        )
        _logger.info(
            "BM25 index built for %s with %d documents", collection_name, len(texts)
        )

    def invalidate(self, collection_name: str) -> None:
        self._indexes.pop(collection_name, None)

    def search(
        self,
        collection_name: str,
        query: str,
        *,
        top_k: int = 20,
    ) -> list[KeywordSearchResult]:
        index = self._indexes.get(collection_name)
        if index is None:
            return []

        tokenized_query = _tokenize(query)
        scores = index.bm25.get_scores(tokenized_query)

        # 取 top_k
        ranked = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:top_k]

        # 归一化分数到 [0,1]
        max_score = ranked[0][1] if ranked else 1.0

        results: list[KeywordSearchResult] = []
        for idx, raw_score in ranked:
            if raw_score <= 0:
                continue
            results.append(
                KeywordSearchResult(
                    text=index.texts[idx],
                    score=raw_score / max_score if max_score > 0 else 0.0,
                    metadata=index.metadatas[idx],
                )
            )
        return results


class BM25OkapiWrapper:
    def __init__(
        self,
        bm25: object,
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        self.bm25 = bm25
        self.texts = texts
        self.metadatas = metadatas


def _tokenize(text: str) -> list[str]:
    """简单的中英文分词：英文按空白+标点，中文按字。"""
    import re

    tokens: list[str] = []
    # 匹配中文连续字符、英文单词、数字
    for match in re.finditer(r"[一-鿿]+|[a-zA-Z]+|\d+", text.lower()):
        token = match.group()
        if re.match(r"[一-鿿]", token):
            # 中文按 bigram 切分
            tokens.extend(token[i : i + 2] for i in range(len(token)))
        else:
            tokens.append(token)
    return tokens


# 全局单例
keyword_engine = KeywordSearchEngine()
