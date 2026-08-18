from dataclasses import dataclass, field
from datetime import date
from typing import TypedDict

from pydantic import BaseModel


class Source(TypedDict):
    id: int
    title: str
    url: str


class CitationRepo:
    """Store of web sources, keyed by url, with sequential friendly ids.

    Seeding with `known` restores the sources registered on earlier turns of a
    conversation, so ids stay stable across turns and the model can cite a
    source it saw in the history. `referenced` is filled by the citations
    capability's output hook: the subset of sources the final answer actually
    cites, in id order.
    """

    def __init__(self, known: list[Source] | None = None) -> None:
        self._by_url: dict[str, Source] = {s['url']: s for s in known or []}
        self.referenced: list[Source] = []

    def register(self, title: str, url: str) -> int:
        if url not in self._by_url:
            next_id = max((s['id'] for s in self._by_url.values()), default=0) + 1
            self._by_url[url] = Source(id=next_id, title=title, url=url)
        return self._by_url[url]['id']

    def sources(self) -> list[Source]:
        return sorted(self._by_url.values(), key=lambda s: s['id'])


class Position(BaseModel):
    ticker: str
    name: str
    quantity: float
    cost_basis: float
    currency: str


class Portfolio(BaseModel):
    as_of: date
    cash: float
    currency: str
    positions: list[Position]


@dataclass
class AdvisorDeps:
    portfolio: Portfolio
    citations: CitationRepo = field(default_factory=CitationRepo)
