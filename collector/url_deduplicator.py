#!/usr/bin/env python3
"""URL deduplication and caching system for Tamil source collection."""

import hashlib
import json
from pathlib import Path


class URLDeduplicator:
    """Maintains a local cache of collected URLs to prevent re-fetching."""
    
    def __init__(self, cache_file: str | Path):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.seen_hashes: set[str] = set()
        self.seen_urls: dict[str, dict] = {}
        self._load_cache()
    
    def _load_cache(self) -> None:
        """Load existing cache from disk."""
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                self.seen_urls = data.get("urls", {})
                self.seen_hashes = set(data.get("hashes", []))
            except Exception as e:
                print(f"WARNING Failed to load cache: {e}")
                self.seen_urls = {}
                self.seen_hashes = set()
    
    def _save_cache(self) -> None:
        """Save cache to disk."""
        try:
            data = {
                "urls": self.seen_urls,
                "hashes": list(self.seen_hashes),
                "updated_at": __import__("datetime").datetime.now().isoformat(),
            }
            self.cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"WARNING Failed to save cache: {e}")
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL to canonical form for comparison."""
        url = url.strip().lower()
        # Remove trailing slashes
        url = url.rstrip("/")
        # Remove common tracking params
        if "?" in url:
            base, query = url.split("?", 1)
            params = query.split("&")
            clean_params = [p for p in params if not any(track in p.lower() for track in ("utm_", "ref=", "src="))]
            url = f"{base}?{'&'.join(sorted(clean_params))}" if clean_params else base
        return url
    
    def _hash_url(self, url: str) -> str:
        """Create SHA1 hash of normalized URL."""
        normalized = self._normalize_url(url)
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    
    def has_seen(self, url: str) -> bool:
        """Check if URL has been collected before."""
        url_hash = self._hash_url(url)
        return url_hash in self.seen_hashes
    
    def add_url(self, url: str, metadata: dict | None = None) -> None:
        """Add URL to cache."""
        url_hash = self._hash_url(url)
        if url_hash not in self.seen_hashes:
            self.seen_hashes.add(url_hash)
            self.seen_urls[url_hash] = {
                "url": url,
                "normalized": self._normalize_url(url),
                "metadata": metadata or {},
                "added_at": __import__("datetime").datetime.now().isoformat(),
            }
            self._save_cache()
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        return {
            "total_urls": len(self.seen_hashes),
            "cache_file": str(self.cache_file),
        }
