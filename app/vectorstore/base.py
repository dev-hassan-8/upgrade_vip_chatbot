from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorDocument:
    id: str
    text: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievedChunk:
    id: str
    text: str
    metadata: dict[str, Any]
    score: float


class VectorStore(ABC):
    @abstractmethod
    def reset_collection(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_documents(self, documents: list[VectorDocument]) -> None:
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        raise NotImplementedError

    @abstractmethod
    def count(self) -> int:
        raise NotImplementedError
