#!/usr/bin/env python3
"""Collect Tamil colloquial dialogue data from multiple sources."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from readability import Document

try:
    from youtube_transcript_api import YouTubeTranscriptApi

    HAS_YOUTUBE_API = True
except ImportError:
    HAS_YOUTUBE_API = False

try:
    from .url_deduplicator import URLDeduplicator
except ImportError:
    from url_deduplicator import URLDeduplicator

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

REDDIT_HEADERS = {
    "User-Agent": "python:tamil-colloquial-collector:v2.0 (by /u/tamillearner)"
}

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "ref_src",
    "source",
    "src",
}
BLOCKED_SCHEMES = {"javascript", "mailto"}
LOW_SIGNAL_DOMAINS = {
    "facebook.com",
    "m.facebook.com",
    "x.com",
    "twitter.com",
    "instagram.com",
    "tiktok.com",
}
LOW_SIGNAL_TITLE_TOKENS = {
    "dictionary",
    "announcement",
    "megathread",
    "wall art",
    "subscribe",
}


@dataclass
class DialogueSource:
    source_type: str
    url: str
    title: str
    content: str
    language: str
    fetch_status: str
    fetched_at: str
    metadata: dict


@dataclass
class SearchResult:
    query: str
    rank: int
    title: str
    url: str
    normalized_url: str
    domain: str
    snippet: str


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def timestamp_slug() -> str:
    return datetime.now().astimezone().strftime("%Y_%m_%d_%H%M%S")


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def decode_ddg_redirect(url: str) -> str:
    parsed = urlparse(url)
    if "duckduckgo.com" not in parsed.netloc:
        return url
    query = parse_qs(parsed.query)
    for key in ("uddg", "u3", "rut", "u"):
        if key in query and query[key]:
            return unquote(query[key][0])
    return url


def normalize_url(url: str) -> str:
    url = decode_ddg_redirect(url)
    parsed = urlparse(url)
    if not parsed.scheme or parsed.scheme.lower() in BLOCKED_SCHEMES:
        return ""
    query_pairs = []
    for key, values in parse_qs(parsed.query, keep_blank_values=False).items():
        if key.lower() not in TRACKING_PARAMS:
            for value in values:
                query_pairs.append((key, value))
    query_pairs.sort()
    query = "&".join(f"{quote_plus(k)}={quote_plus(v)}" for k, v in query_pairs)
    path = parsed.path or "/"
    normalized = parsed._replace(query=query, fragment="", path=path.rstrip("/") or "/")
    return normalized.geturl()


def extract_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def detect_language(text: str) -> str:
    if re.search(r"[\u0b80-\u0bff]", text):
        return "ta"
    if re.search(r"[a-zA-Z]", text):
        return "en"
    return "unknown"


def fingerprint_text(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9\u0b80-\u0bff ]", " ", normalize_whitespace(text).lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def clean_page_text(text: str, max_chars: int = 4000) -> str:
    text = normalize_whitespace(text)
    boilerplate_patterns = [
        r"cookie(s)? policy",
        r"subscribe now",
        r"sign up",
        r"all rights reserved",
        r"advertisement",
        r"accept cookies",
        r"share save hide report",
    ]
    for pattern in boilerplate_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = normalize_whitespace(text)
    return text[:max_chars].strip()


def extract_readable_text(page_html: str) -> tuple[str, str]:
    try:
        doc = Document(page_html)
        title = normalize_whitespace(doc.short_title())
        summary_html = doc.summary(html_partial=True)
        soup = BeautifulSoup(summary_html, "html.parser")
        text = normalize_whitespace(soup.get_text(" ", strip=True))
        if text:
            return title, text
    except Exception:
        pass

    soup = BeautifulSoup(page_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    title = normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else "")
    text = normalize_whitespace(soup.get_text(" ", strip=True))
    return title, text


def is_low_signal_result(url: str, title: str, snippet: str) -> bool:
    domain = extract_domain(url)
    lowered_title = title.lower()
    if any(token in domain for token in LOW_SIGNAL_DOMAINS):
        return True
    if any(token in lowered_title for token in LOW_SIGNAL_TITLE_TOKENS):
        return True
    combined = f"{title} {snippet}".lower()
    return "dictionary" in combined and "slang" not in combined


def fetch_generic_page(
    session: requests.Session,
    url: str,
    fallback_title: str,
    fallback_snippet: str,
) -> tuple[str, str, str]:
    domain = extract_domain(url)
    if any(token in domain for token in ("youtube.com", "youtu.be")):
        return fallback_title, fallback_snippet, "snippet_only"

    try:
        response = session.get(url, timeout=30, allow_redirects=True)
        response.raise_for_status()
        final_url = normalize_url(response.url)
        title, text = extract_readable_text(response.text)
        content = clean_page_text(text or fallback_snippet)
        return title or fallback_title, content or fallback_snippet, "ok"
    except Exception as exc:
        return fallback_title, clean_page_text(fallback_snippet), f"fallback:{type(exc).__name__}"


def search_query(query: str, top_k: int) -> list[SearchResult]:
    ddgs = DDGS(timeout=20)
    raw_results = ddgs.text(
        query,
        region="in-en",
        safesearch="moderate",
        timelimit="m",
        max_results=top_k,
        backend="duckduckgo",
    )
    results: list[SearchResult] = []
    seen_urls: set[str] = set()

    for item in raw_results:
        title = normalize_whitespace(item.get("title", ""))
        raw_url = normalize_whitespace(item.get("href", ""))
        normalized_url = normalize_url(raw_url)
        if not title or not normalized_url:
            continue
        if normalized_url in seen_urls:
            continue
        snippet = normalize_whitespace(item.get("body", ""))
        if is_low_signal_result(normalized_url, title, snippet):
            continue
        seen_urls.add(normalized_url)
        results.append(
            SearchResult(
                query=query,
                rank=len(results) + 1,
                title=title,
                url=raw_url,
                normalized_url=normalized_url,
                domain=extract_domain(normalized_url),
                snippet=snippet,
            )
        )
        if len(results) >= top_k:
            break
    return results


def search_ddgs(session: requests.Session, query: str, top_k: int = 5, deduplicator: URLDeduplicator | None = None) -> list[DialogueSource]:
    results: list[DialogueSource] = []
    try:
        for item in search_query(query, top_k):
            if deduplicator and deduplicator.has_seen(item.normalized_url):
                print(f"DEBUG Skipping already-collected URL: {item.title[:50]}", file=sys.stderr)
                continue

            title, content, fetch_status = fetch_generic_page(
                session,
                item.normalized_url,
                item.title,
                item.snippet,
            )
            if should_skip_source(content, title):
                continue

            detected_lang = detect_language(content or title)
            if detected_lang != "ta":
                continue

            if deduplicator:
                deduplicator.add_url(item.normalized_url, {"title": title, "source": "ddgs"})

            results.append(
                DialogueSource(
                    source_type="ddgs",
                    url=item.normalized_url,
                    title=title,
                    content=content,
                    language=detected_lang,
                    fetch_status=fetch_status,
                    fetched_at=now_iso(),
                    metadata={
                        "query": query,
                        "rank": item.rank,
                        "domain": item.domain,
                        "content_fingerprint": fingerprint_text(content or title),
                    },
                )
            )
    except Exception as exc:
        print(f"WARNING DDGS search failed for '{query}': {exc}", file=sys.stderr)
    return results


def build_absolute_reddit_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return normalize_url(url)
    if url.startswith("/"):
        return normalize_url(f"https://old.reddit.com{url}")
    return normalize_url(f"https://old.reddit.com/{url.lstrip('/')}")


def extract_reddit_post_text(soup: BeautifulSoup, max_comments: int = 6) -> str:
    blocks: list[str] = []

    selftext = soup.select_one("div.expando div.usertext-body div.md")
    if selftext:
        blocks.append(selftext.get_text("\n", strip=True))

    for idx, comment in enumerate(soup.select("div.comment div.usertext-body div.md"), start=1):
        if idx > max_comments:
            break
        comment_text = comment.get_text("\n", strip=True)
        if len(comment_text.split()) < 3:
            continue
        blocks.append(f"Comment {idx}: {comment_text}")

    return clean_page_text("\n".join(blocks), max_chars=5000)


def fetch_reddit_post_details(session: requests.Session, post_url: str, fallback_title: str) -> tuple[str, str]:
    try:
        response = session.get(post_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        content = extract_reddit_post_text(soup)
        if content:
            return content, "ok"
        return fallback_title, "title_only"
    except Exception as exc:
        return fallback_title, f"fallback:{type(exc).__name__}"


def scrape_reddit_subreddit(subreddit: str, max_posts: int = 20) -> list[DialogueSource]:
    results: list[DialogueSource] = []
    url = f"https://old.reddit.com/r/{subreddit}/"
    session = requests.Session()
    session.headers.update(REDDIT_HEADERS)

    while url and len(results) < max_posts:
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            for thing in soup.select("div#siteTable > div.thing"):
                if len(results) >= max_posts:
                    break

                title_el = thing.select_one("a.title")
                if not title_el:
                    continue

                title = html.unescape(title_el.get_text(strip=True))
                permalink = thing.get("data-permalink") or title_el.get("href", "")
                post_url = build_absolute_reddit_url(permalink)
                if not post_url:
                    continue

                content, fetch_status = fetch_reddit_post_details(session, post_url, title)
                if should_skip_source(content, title):
                    continue

                author = thing.get("data-author", "")
                score = thing.get("data-score", "0")
                comments_count = thing.get("data-comments-count", "0")
                results.append(
                    DialogueSource(
                        source_type="reddit",
                        url=post_url,
                        title=title,
                        content=content,
                        language=detect_language(content or title),
                        fetch_status=fetch_status,
                        fetched_at=now_iso(),
                        metadata={
                            "subreddit": subreddit,
                            "author": author,
                            "score": int(score) if str(score).isdigit() else 0,
                            "comments": int(comments_count) if str(comments_count).isdigit() else 0,
                            "content_fingerprint": fingerprint_text(content or title),
                        },
                    )
                )

            nxt = soup.select_one("span.next-button a")
            url = nxt["href"] if nxt else None
            time.sleep(1.2)
        except Exception as exc:
            print(f"WARNING Reddit scraping failed for r/{subreddit}: {exc}", file=sys.stderr)
            break

    return results


def collect_reddit_data(max_posts_per_sub: int = 15, deduplicator: URLDeduplicator | None = None) -> list[DialogueSource]:
    subreddits = ["tamil", "TamilNadu", "Chennai", "Kollywood", "languagelearning"]
    results: list[DialogueSource] = []
    for subreddit in subreddits:
        print(f"INFO Scraping r/{subreddit}...", file=sys.stderr)
        results.extend(scrape_reddit_subreddit(subreddit, max_posts_per_sub, deduplicator))
    return results


def extract_youtube_video_id(url: str) -> str | None:
    patterns = [
        r"(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&\n?#]+)",
        r"youtube\.com\/embed\/([^&\n?#]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_youtube_transcript(video_id: str, max_chars: int = 50000) -> dict | None:
    """Fetch YouTube transcript for a video, with generous character limit.
    
    Args:
        video_id: YouTube video ID
        max_chars: Maximum characters to return (default 50k for full movies)
    
    Returns:
        dict with keys: 'tamil', 'english', 'has_dual_subtitles'
    """
    if not HAS_YOUTUBE_API:
        return None

    try:
        result = {
            'tamil': None,
            'english': None,
            'has_dual_subtitles': False,
        }
        
        # Try to fetch Tamil subtitles
        try:
            tamil_transcript = YouTubeTranscriptApi().fetch(video_id, languages=["ta"])
            tamil_chunks = []
            for item in tamil_transcript:
                text = item.text.strip() if hasattr(item, 'text') else str(item).strip()
                if text:
                    tamil_chunks.append(text)
            tamil_text = " ".join(tamil_chunks)
            if tamil_text and len(tamil_text) >= 50:
                result['tamil'] = clean_page_text(tamil_text, max_chars=max_chars)
        except Exception:
            pass
        
        # Try to fetch English subtitles
        try:
            english_transcript = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
            english_chunks = []
            for item in english_transcript:
                text = item.text.strip() if hasattr(item, 'text') else str(item).strip()
                if text:
                    english_chunks.append(text)
            english_text = " ".join(english_chunks)
            if english_text and len(english_text) >= 50:
                result['english'] = clean_page_text(english_text, max_chars=max_chars)
        except Exception:
            pass
        
        # Check if we have both Tamil and English subtitles
        if result['tamil'] and result['english']:
            result['has_dual_subtitles'] = True
        
        # Return None if no useful content
        if not result['tamil'] and not result['english']:
            return None
        
        return result
    except Exception as e:
        print(f"DEBUG YouTube transcript error for {video_id}: {e}", file=sys.stderr)
        return None


def collect_youtube_data(search_queries: list[str], max_per_query: int = 5) -> list[DialogueSource]:
    """Collect Tamil YouTube transcripts.
    Strategy: Use proven Tamil-subtitle videos + DDGS search for Tamil movie subtitles.
    """
    results: list[DialogueSource] = []
    if not HAS_YOUTUBE_API:
        print("WARNING youtube-transcript-api not installed. Skipping YouTube collection.", file=sys.stderr)
        return results

    # ================================================================
    # Proven Tamil subtitle videos (verified to have Tamil subtitles)
    # Format: (video_id, title, category)
    # ================================================================
    proven_tamil_videos: list[tuple[str, str, str]] = [
        ("EnnMBmn__lo", "Aan Paavam (1985 Tamil comedy) - Tamil subs", "movie"),
        ("s3dBN0G-kog", "Vezham Tamil Full Movie - Tamil subs", "movie"),
        ("qyI6p-PBpi0", "Tamil Full Movie HD - Tamil subs", "movie"),
    ]

    # ================================================================
    # Phase 1: Collect from proven Tamil subtitle videos
    # ================================================================
    direct_ids = set()
    for video_id, title, category in proven_tamil_videos:
        if video_id in direct_ids:
            continue
        direct_ids.add(video_id)

        print(f"INFO [PROVEN] Fetching: {title} (ID: {video_id})...", file=sys.stderr)
        try:
            transcript_data = get_youtube_transcript(video_id)
            if transcript_data and transcript_data.get('tamil'):
                tamil_text = transcript_data['tamil']
                english_text = transcript_data.get('english')
                has_dual = transcript_data.get('has_dual_subtitles', False)
                
                if not should_skip_source(tamil_text, title):
                    results.append(
                        DialogueSource(
                            source_type="youtube",
                            url=f"https://www.youtube.com/watch?v={video_id}",
                            title=title,
                            content=tamil_text,
                            language="ta",
                            fetch_status="ok",
                            fetched_at=now_iso(),
                            metadata={
                                "video_id": video_id,
                                "category": category,
                                "content_fingerprint": fingerprint_text(tamil_text),
                                "has_dual_subtitles": has_dual,
                                "english_subtitle": english_text if english_text else None,
                            },
                        )
                    )
                print(f"INFO ✓ {title} ({len(tamil_text)} chars, dual={'Y' if has_dual else 'N'})", file=sys.stderr)
            else:
                print(f"INFO ✗ Skipped: {title}", file=sys.stderr)
        except Exception as exc:
            print(f"DEBUG Error fetching {title}: {exc}", file=sys.stderr)

    # ================================================================
    # Phase 2: DDGS search for more Tamil movies with subtitles
    # Only search for Tamil movies that have subtitles (English or Tamil)
    # ================================================================
    ddgs_search_queries = [
        "tamil english subtitles youtube",
        "tamil movie english subtitles youtube",
        "tamil kollywood movie english subtitles youtube",
        "tamil dubbed movie english subtitles youtube",
        "tamil full movie with english subtitles",
        "tamil movie with english subtitles youtube",
        "tamil full movie hd youtube",
        "tamil movie with english subs youtube",
        "tamil dubbed movie english subs youtube",
    ]
    ddgs_search_queries.extend(search_queries)

    seen_youtube_ids = direct_ids.copy()
    tamil_videos_found = 0
    english_only_videos = 0

    for query in ddgs_search_queries:
        youtube_query = f"{query} site:youtube.com"
        print(f"INFO DDGS search: '{query}'...", file=sys.stderr)
        try:
            for item in search_query(youtube_query, max_per_query):
                video_id = extract_youtube_video_id(item.normalized_url)
                if not video_id:
                    continue
                if video_id in seen_youtube_ids:
                    continue
                seen_youtube_ids.add(video_id)

                transcript_data = get_youtube_transcript(video_id)
                if not transcript_data or not transcript_data.get('tamil'):
                    continue
                
                tamil_text = transcript_data['tamil']
                english_text = transcript_data.get('english')
                has_dual = transcript_data.get('has_dual_subtitles', False)
                
                if should_skip_source(tamil_text, item.title):
                    continue

                tamil_chars = sum(1 for c in tamil_text if '\u0b80' <= c <= '\u0bff')
                tamil_pct = tamil_chars / len(tamil_text) * 100 if len(tamil_text) > 0 else 0

                # Accept if it has significant Tamil content (>30% Tamil chars)
                # OR if it's a Tamil movie with English subtitles (we can still use it)
                if tamil_pct > 30:
                    results.append(
                        DialogueSource(
                            source_type="youtube",
                            url=item.normalized_url,
                            title=item.title,
                            content=tamil_text,
                            language="ta",
                            fetch_status="ok",
                            fetched_at=now_iso(),
                            metadata={
                                "video_id": video_id,
                                "query": query,
                                "tamil_pct": round(tamil_pct, 1),
                                "content_fingerprint": fingerprint_text(tamil_text),
                                "has_dual_subtitles": has_dual,
                                "english_subtitle": english_text if english_text else None,
                            },
                        )
                    )
                    tamil_videos_found += 1
                    print(f"INFO ✓ Tamil-subs: {item.title[:60]} ({len(tamil_text)} chars, {tamil_pct:.0f}% Tamil, dual={'Y' if has_dual else 'N'})", file=sys.stderr)
                elif "tamil" in item.title.lower() or "kollywood" in item.title.lower():
                    # Accept Tamil movies with English subtitles too (useful for comparison)
                    if english_text:
                        results.append(
                            DialogueSource(
                                source_type="youtube",
                                url=item.normalized_url,
                                title=item.title,
                                content=english_text,
                                language="en",  # Mark as English subs
                                fetch_status="ok",
                                fetched_at=now_iso(),
                                metadata={
                                    "video_id": video_id,
                                    "query": query,
                                    "tamil_pct": round(tamil_pct, 1),
                                    "content_fingerprint": fingerprint_text(english_text),
                                    "has_dual_subtitles": has_dual,
                                    "english_subtitle": english_text,
                                },
                            )
                        )
                        english_only_videos += 1
                        print(f"INFO ✓ Eng-subs (Tamil movie): {item.title[:60]} ({len(english_text)} chars, {tamil_pct:.0f}% Tamil)", file=sys.stderr)
        except Exception as exc:
            print(f"DEBUG DDGS search failed for '{query}': {exc}", file=sys.stderr)

    print(f"INFO YouTube collection summary: {tamil_videos_found} Tamil-subs, {english_only_videos} Eng-subs videos", file=sys.stderr)
    return results


def should_skip_source(content: str, title: str = "") -> bool:
    if not content or len(content.strip()) < 40:
        return True

    combined = f"{title} {content}".lower()
    if any(token in combined for token in ("dictionary", "megathread", "announcement", "wall art")):
        return True

    special_ratio = len(re.findall(r"[^a-zA-Z0-9\s\u0b80-\u0bff]", content)) / max(1, len(content))
    if special_ratio > 0.45:
        return True

    word_count = len(content.split())
    return word_count < 6


def deduplicate_sources(sources: list[DialogueSource]) -> list[DialogueSource]:
    selected_by_url: dict[str, DialogueSource] = {}
    selected_by_fingerprint: dict[str, DialogueSource] = {}

    for source in sources:
        content = clean_page_text(source.content)
        if should_skip_source(content, source.title):
            continue

        source.content = content
        fingerprint = source.metadata.get("content_fingerprint") or fingerprint_text(content)
        source.metadata["content_fingerprint"] = fingerprint

        existing = selected_by_url.get(source.url)
        if existing is None or len(source.content) > len(existing.content):
            selected_by_url[source.url] = source

        existing = selected_by_fingerprint.get(fingerprint)
        if existing is None or len(source.content) > len(existing.content):
            selected_by_fingerprint[fingerprint] = source

    fingerprints = {item.metadata["content_fingerprint"] for item in selected_by_fingerprint.values()}
    deduped = [item for item in selected_by_url.values() if item.metadata["content_fingerprint"] in fingerprints]
    deduped.sort(key=lambda item: (item.source_type != "reddit", -len(item.content)))
    return deduped


def build_agent_input(sources: list[DialogueSource]) -> dict:
    return {
        "task_name": "tamil_colloquial",
        "generated_at": now_iso(),
        "source_summary": {
            "total_sources": len(sources),
            "by_type": {
                "reddit": len([s for s in sources if s.source_type == "reddit"]),
                "youtube": len([s for s in sources if s.source_type == "youtube"]),
                "ddgs": len([s for s in sources if s.source_type == "ddgs"]),
            },
            "by_language": {
                "tamil": len([s for s in sources if s.language == "ta"]),
                "english": len([s for s in sources if s.language == "en"]),
                "unknown": len([s for s in sources if s.language == "unknown"]),
            },
        },
        "sources": [asdict(source) for source in sources],
        "instructions": {
            "focus": "Extract authentic colloquial Tamil dialogues",
            "quality_filter": "Prefer source bodies, comments, and transcripts over snippets",
            "output_format": "dialogue candidates with colloquial scoring and risk annotations",
        },
    }


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect Tamil colloquial dialogue data")
    parser.add_argument("--output-dir", required=True, help="Output directory path")
    parser.add_argument("--ddgs-queries", nargs="+", default=[], help="DDGS search queries (for web pages)")
    parser.add_argument("--reddit-max-posts", type=int, default=15, help="Max posts per subreddit")
    parser.add_argument("--youtube-queries", nargs="+", default=[], help="YouTube search queries (supplements curated list)")
    parser.add_argument("--youtube-max-per-query", type=int, default=5, help="Max YouTube results per DDGS query")
    parser.add_argument("--no-youtube", action="store_true", help="Skip YouTube collection")
    parser.add_argument("--no-ddgs", action="store_true", help="Skip DDGS collection")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = timestamp_slug()
    session = make_session()

    print("="*70, file=sys.stderr)
    print("INFO Tamil Colloquial Collector starting...", file=sys.stderr)
    print(f"INFO Timestamp: {run_stamp}", file=sys.stderr)
    print("="*70, file=sys.stderr)

    all_sources: list[DialogueSource] = []

    # Phase 1: DDGS search for Tamil web pages (forums, articles, etc.)
    if not args.no_ddgs and args.ddgs_queries:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"INFO Phase 1: DDGS Web Search ({len(args.ddgs_queries)} queries)", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(args.ddgs_queries))) as executor:
            futures = [
                executor.submit(search_ddgs, session, query, 5)
                for query in args.ddgs_queries
            ]
            for future in concurrent.futures.as_completed(futures):
                all_sources.extend(future.result())
    elif not args.no_ddgs and not args.ddgs_queries:
        # Default DDGS queries for Tamil content
        print(f"\n{'='*70}", file=sys.stderr)
        print("INFO Phase 1: DDGS Web Search (default queries)", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        default_ddgs = [
            "tamil colloquial conversation",
            "அன்றாட தமிழ் பேச்சு",
            "tamil slang phrases",
            "tamil casual dialogue",
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(default_ddgs))) as executor:
            futures = [
                executor.submit(search_ddgs, session, query, 5)
                for query in default_ddgs
            ]
            for future in concurrent.futures.as_completed(futures):
                all_sources.extend(future.result())

    # Phase 2: YouTube transcript collection (PRIMARY source)
    if not args.no_youtube and HAS_YOUTUBE_API:
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"INFO Phase 2: YouTube Transcript Collection", file=sys.stderr)
        print(f"{'='*70}", file=sys.stderr)
        all_sources.extend(collect_youtube_data(args.youtube_queries, args.youtube_max_per_query))
    elif args.no_youtube:
        print("\nINFO Skipping YouTube collection (--no-youtube flag)", file=sys.stderr)

    # Phase 3: Reddit (disabled by default)
    # if not args.no_reddit:
    #     print(f"\nINFO Phase 3: Reddit Collection...", file=sys.stderr)
    #     all_sources.extend(collect_reddit_data(args.reddit_max_posts))

    # Phase 4: Deduplicate and finalize
    print(f"\n{'='*70}", file=sys.stderr)
    print(f"INFO Phase 3: Deduplication & Finalization ({len(all_sources)} raw sources)", file=sys.stderr)
    print(f"{'='*70}", file=sys.stderr)
    deduped = deduplicate_sources(all_sources)
    print(f"INFO Final deduplicated sources: {len(deduped)}", file=sys.stderr)

    # Print summary
    by_type = {}
    by_lang = {}
    for s in deduped:
        by_type[s.source_type] = by_type.get(s.source_type, 0) + 1
        by_lang[s.language] = by_lang.get(s.language, 0) + 1
    print(f"\n  By type: {by_type}", file=sys.stderr)
    print(f"  By language: {by_lang}", file=sys.stderr)

    agent_input = build_agent_input(deduped)
    raw_file = output_dir / f"tamil_raw_sources_{run_stamp}.json"
    write_json(raw_file, [asdict(s) for s in deduped])
    agent_input_file = output_dir / "tamil_agent_input.json"
    write_json(agent_input_file, agent_input)

    print(f"\nINFO Raw sources: {raw_file}", file=sys.stderr)
    print(f"INFO Agent input: {agent_input_file}", file=sys.stderr)
    print(agent_input_file, file=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
