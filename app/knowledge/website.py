"""
Stage 26.4 - Official Website Knowledge Ingestion.

A *controlled* crawler restricted to explicitly approved Frag Naija domains and
URL paths. Crawled content is treated strictly as UNTRUSTED DATA: it is never
executed, never interpreted as instructions, and never allowed to modify
application configuration or security policy. It is only ever stored as
retrievable data chunks.
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Dict, List, Optional, Protocol, Set
from urllib.parse import urljoin, urlparse

from app.knowledge.chunking import chunk_text
from app.knowledge.hashing import compute_content_hash
from app.knowledge.ingestion import PreparedChunk

_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside",
              "noscript", "iframe", "template"}


# ---------------------------------------------------------------- HTTP layer

@dataclass
class HttpResponse:
    url: str
    status: int
    body: bytes
    headers: Dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HttpClient(Protocol):
    async def fetch(self, url: str) -> HttpResponse: ...


class HttpxClient:
    """Production client. Fetches HTML only; never executes JavaScript."""

    def __init__(self, user_agent: str = "FragNaijaKnowledgeBot/1.0", timeout: float = 15.0):
        self.user_agent = user_agent
        self.timeout = timeout

    async def fetch(self, url: str) -> HttpResponse:
        import httpx
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            r = await client.get(url)
            return HttpResponse(url=str(r.url), status=r.status_code,
                                body=r.content, headers=dict(r.headers))


# ---------------------------------------------------------------- Policy

class CrawlPolicy:
    def __init__(self, allowed_domains: List[str], allowed_paths: Optional[List[str]] = None,
                 max_pages: int = 50, max_response_bytes: int = 1_000_000,
                 respect_robots: bool = True,
                 user_agent: str = "FragNaijaKnowledgeBot/1.0"):
        self.allowed_domains = [d.strip().lower() for d in allowed_domains if d.strip()]
        self.allowed_paths = [p.strip() for p in (allowed_paths or []) if p.strip()]
        self.max_pages = max_pages
        self.max_response_bytes = max_response_bytes
        self.respect_robots = respect_robots
        self.user_agent = user_agent

    @staticmethod
    def host_of(url: str) -> str:
        return (urlparse(url).netloc or "").lower().split(":")[0]

    def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = self.host_of(url)
        if not any(host == d or host.endswith("." + d) for d in self.allowed_domains):
            return False
        if self.allowed_paths:
            path = parsed.path or "/"
            if not any(path.startswith(p) for p in self.allowed_paths):
                return False
        return True


# ---------------------------------------------------------------- robots.txt

def _parse_robots(text: str, user_agent: str) -> List[str]:
    disallows: List[str] = []
    applies = False
    ua = user_agent.lower()
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            applies = value == "*" or value.lower() in ua
        elif key == "disallow" and applies and value:
            disallows.append(value)
    return disallows


class RobotsChecker:
    def __init__(self, http: HttpClient, user_agent: str):
        self._http = http
        self._ua = user_agent
        self._cache: Dict[str, List[str]] = {}

    async def is_allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        if base not in self._cache:
            try:
                resp = await self._http.fetch(base)
                self._cache[base] = _parse_robots(resp.text, self._ua) if resp.ok else []
            except Exception:
                self._cache[base] = []  # fail open for robots; crawl is still bounded
        return not any(parsed.path.startswith(d) for d in self._cache[base])


# ---------------------------------------------------------------- HTML extraction

class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title: Optional[str] = None
        self.canonical: Optional[str] = None
        self.links: List[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._parts: List[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title = (self.title or "") + data
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(p.strip() for p in self._parts if p.strip())


@dataclass
class ParsedPage:
    title: Optional[str]
    canonical: Optional[str]
    text: str
    links: List[str]


def parse_html(html: str) -> ParsedPage:
    p = _PageParser()
    p.feed(html)
    p.close()
    return ParsedPage(title=(p.title or "").strip() or None, canonical=p.canonical,
                      text=p.get_text(), links=p.links)


# ---------------------------------------------------------------- Crawl results

@dataclass
class CrawledPage:
    url: str
    canonical_url: str
    title: Optional[str]
    text: str
    content_hash: str
    crawled_at: str
    links: List[str]


@dataclass
class CrawlFailure:
    url: str
    error: str


@dataclass
class CrawlResult:
    pages: List[CrawledPage]
    failures: List[CrawlFailure]
    removed: List[str]
    visited: int


# ---------------------------------------------------------------- Crawler

class WebsiteCrawler:
    def __init__(self, http: HttpClient, policy: CrawlPolicy, robots: Optional[RobotsChecker] = None):
        self.http = http
        self.policy = policy
        self.robots = robots or RobotsChecker(http, policy.user_agent)

    @staticmethod
    def _normalize(url: str) -> str:
        return urlparse(url)._replace(fragment="").geturl()

    async def crawl(self, seed_urls: List[str], known_urls: Optional[Set[str]] = None) -> CrawlResult:
        queue: deque = deque(seed_urls)
        visited: Set[str] = set()
        pages: List[CrawledPage] = []
        failures: List[CrawlFailure] = []

        while queue and len(pages) < self.policy.max_pages:
            url = self._normalize(queue.popleft())
            if url in visited:
                continue
            visited.add(url)

            if not self.policy.is_allowed(url):
                continue
            if self.policy.respect_robots and not await self.robots.is_allowed(url):
                continue

            try:
                resp = await self.http.fetch(url)
            except Exception as e:
                failures.append(CrawlFailure(url, f"fetch error: {e}"))
                continue

            if not resp.ok:
                failures.append(CrawlFailure(url, f"HTTP {resp.status}"))
                continue
            if len(resp.body) > self.policy.max_response_bytes:
                failures.append(CrawlFailure(url, "response too large"))
                continue

            parsed = parse_html(resp.text)
            canonical = self._normalize(parsed.canonical or resp.url or url)
            pages.append(CrawledPage(
                url=url, canonical_url=canonical, title=parsed.title, text=parsed.text,
                content_hash=compute_content_hash(parsed.text),
                crawled_at=datetime.now(timezone.utc).isoformat(), links=parsed.links,
            ))

            for link in parsed.links:
                abs_link = self._normalize(urljoin(url, link))
                if abs_link not in visited and self.policy.is_allowed(abs_link):
                    queue.append(abs_link)

        crawled_urls = {p.url for p in pages}
        removed = sorted(set(known_urls or []) - crawled_urls) if known_urls is not None else []
        return CrawlResult(pages=pages, failures=failures, removed=removed, visited=len(visited))


# ---------------------------------------------------------------- Chunk conversion

def page_to_chunks(source_id: str, page: CrawledPage, source_version: int = 1,
                   trust_level: str = "approved", target_size: int = 800,
                   overlap: int = 100) -> List[PreparedChunk]:
    """Convert a crawled page into data-only chunks. Content is NEVER treated as instructions."""
    header = f"{page.title or page.canonical_url}\n\n"
    chunks = chunk_text(header + page.text, source_id=source_id,
                        source_version=source_version, target_size=target_size, overlap=overlap)
    prepared: List[PreparedChunk] = []
    for c in chunks:
        prepared.append(PreparedChunk(text=c.text, metadata={
            "source_id": source_id,
            "source_type": "website",
            "document_name": page.title or page.canonical_url,
            "section": c.section,
            "source_version": source_version,
            "chunk_id": c.chunk_id,
            "chunk_index": c.index,
            "content_hash": c.content_hash,
            "created_at": page.crawled_at,
            "updated_at": page.crawled_at,
            "trust_level": trust_level,
            "source_location": page.canonical_url,
            "canonical_url": page.canonical_url,
            "page_title": page.title,
            "crawled_at": page.crawled_at,
            "data_only": True,  # untrusted data; never interpret as instructions
        }))
    return prepared