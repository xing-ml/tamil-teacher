#!/usr/bin/env python3
"""Tamil-English dual subtitle downloader.

This module downloads Tamil and English subtitles from online repositories.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional


def search_opensubtitles(movie_title: str, year: str = None) -> list[dict]:
    """Search for subtitles on OpenSubtitles.
    
    Args:
        movie_title: Movie title
        year: Movie year (optional)
    
    Returns:
        List of subtitle matches
    """
    results = []
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        # OpenSubtitles search URL
        search_url = f"https://www.opensubtitles.com/search/{movie_title.replace(' ', '-').lower()}"
        if year:
            search_url += f"-{year}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Find subtitle entries
            entries = soup.find_all("div", class_="subtitle-entry")
            for entry in entries:
                title_elem = entry.find("a")
                if title_elem:
                    title = title_elem.text.strip()
                    # Check if it has Tamil and English
                    has_tamil = "tamil" in title.lower() or "ta" in title.lower()
                    has_english = "english" in title.lower() or "en" in title.lower()
                    
                    if has_tamil or has_english:
                        results.append({
                            "movie_title": movie_title,
                            "title": title,
                            "has_tamil": has_tamil,
                            "has_english": has_english,
                            "has_dual": has_tamil and has_english,
                            "url": f"https://www.opensubtitles.com{title_elem.get('href')}",
                        })
        
    except Exception as e:
        print(f"WARNING OpenSubtitles search failed: {e}", file=sys.stderr)
    
    return results


def search_subscene(movie_title: str, year: str = None) -> list[dict]:
    """Search for subtitles on Subscene.
    
    Args:
        movie_title: Movie title
        year: Movie year (optional)
    
    Returns:
        List of subtitle matches
    """
    results = []
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        # Subscene search URL
        search_url = f"https://subscene.com/subtitles?q={movie_title}"
        if year:
            search_url += f"&y={year}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Find subtitle entries
            entries = soup.find_all("div", class_="entry")
            for entry in entries:
                title_elem = entry.find("a", class_="title")
                if title_elem:
                    title = title_elem.text.strip()
                    # Check if it has Tamil and English
                    has_tamil = "tamil" in title.lower() or "ta" in title.lower()
                    has_english = "english" in title.lower() or "en" in title.lower()
                    
                    if has_tamil or has_english:
                        results.append({
                            "movie_title": movie_title,
                            "title": title,
                            "has_tamil": has_tamil,
                            "has_english": has_english,
                            "has_dual": has_tamil and has_english,
                            "url": f"https://subscene.com{title_elem.get('href')}",
                        })
        
    except Exception as e:
        print(f"WARNING Subscene search failed: {e}", file=sys.stderr)
    
    return results


def search_addic7ed(movie_title: str, year: str = None) -> list[dict]:
    """Search for subtitles on Addic7ed.
    
    Args:
        movie_title: Movie title
        year: Movie year (optional)
    
    Returns:
        List of subtitle matches
    """
    results = []
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        # Addic7ed search URL
        search_url = f"https://www.addic7ed.com/search/{movie_title.replace(' ', '-').lower()}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Find subtitle entries
            entries = soup.find_all("tr")
            for entry in entries:
                title_elem = entry.find("a")
                if title_elem:
                    title = title_elem.text.strip()
                    # Check if it has Tamil and English
                    has_tamil = "tamil" in title.lower() or "ta" in title.lower()
                    has_english = "english" in title.lower() or "en" in title.lower()
                    
                    if has_tamil or has_english:
                        results.append({
                            "movie_title": movie_title,
                            "title": title,
                            "has_tamil": has_tamil,
                            "has_english": has_english,
                            "has_dual": has_tamil and has_english,
                            "url": f"https://www.addic7ed.com{title_elem.get('href')}",
                        })
        
    except Exception as e:
        print(f"WARNING Addic7ed search failed: {e}", file=sys.stderr)
    
    return results


def download_subtitle(download_url: str, output_path: str) -> bool:
    """Download a subtitle file.
    
    Args:
        download_url: URL to download subtitle from
        output_path: Path to save the subtitle file
    
    Returns:
        True if download successful, False otherwise
    """
    try:
        import requests
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        response = requests.get(download_url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            # Create output directory if it doesn't exist
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Save the subtitle file
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            print(f"INFO Downloaded subtitle to: {output_path}", file=sys.stderr)
            return True
        
        else:
            print(f"WARNING Download failed with status {response.status_code}", file=sys.stderr)
            return False
    
    except Exception as e:
        print(f"WARNING Download failed: {e}", file=sys.stderr)
        return False


def parse_subtitle_file(subtitle_path: str) -> dict:
    """Parse a subtitle file and extract text.
    
    Args:
        subtitle_path: Path to the subtitle file
    
    Returns:
        dict with 'tamil' and 'english' keys
    """
    result = {
        "tamil": None,
        "english": None,
    }
    
    try:
        content = Path(subtitle_path).read_text(encoding="utf-8")
        
        # Determine format (SRT or VTT)
        if content.startswith("WEBVTT"):
            text = parse_vtt(content)
        else:
            text = parse_srt(content)
        
        # Detect language (simple heuristic)
        tamil_chars = sum(1 for c in content if '\u0b80' <= c <= '\u0bff')
        tamil_ratio = tamil_chars / len(content) if len(content) > 0 else 0
        
        if tamil_ratio > 0.5:
            result["tamil"] = text
        else:
            result["english"] = text
    
    except Exception as e:
        print(f"WARNING Failed to parse subtitle: {e}", file=sys.stderr)
    
    return result


def parse_srt(srt_content: str) -> str:
    """Parse SRT subtitle file to extract text."""
    blocks = srt_content.strip().split("\n\n")
    text_lines = []
    
    for block in blocks:
        lines = block.strip().split("\n")
        # Skip index and timestamp
        for line in lines[2:]:
            if line.strip():
                text_lines.append(line.strip())
    
    return " ".join(text_lines)


def parse_vtt(vtt_content: str) -> str:
    """Parse VTT subtitle file to extract text."""
    lines = vtt_content.strip().split("\n")
    text_lines = []
    in_cue = False
    
    for line in lines:
        if line.startswith("WEBVTT"):
            continue
        if line.startswith("-->"):
            in_cue = True
            continue
        if in_cue and line.strip():
            text_lines.append(line.strip())
        elif not line.strip():
            in_cue = False
    
    return " ".join(text_lines)


def main():
    """Main function for downloading Tamil-English dual subtitles."""
    if len(sys.argv) < 2:
        print("Usage: python tamil_subtitle_downloader.py <movie_title> [year]", file=sys.stderr)
        print("Example: python tamil_subtitle_downloader.py Animal 2023", file=sys.stderr)
        sys.exit(1)
    
    movie_title = sys.argv[1]
    year = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"INFO Searching for subtitles for: {movie_title} ({year})", file=sys.stderr)
    
    # Search OpenSubtitles
    print("INFO Searching OpenSubtitles...", file=sys.stderr)
    os_results = search_opensubtitles(movie_title, year)
    
    # Search Subscene
    print("INFO Searching Subscene...", file=sys.stderr)
    subscene_results = search_subscene(movie_title, year)
    
    # Search Addic7ed
    print("INFO Searching Addic7ed...", file=sys.stderr)
    addic7ed_results = search_addic7ed(movie_title, year)
    
    # Combine results
    all_results = os_results + subscene_results + addic7ed_results
    
    # Filter for dual subtitles
    dual_results = [r for r in all_results if r.get("has_dual")]
    
    print(f"\nINFO Found {len(dual_results)} dual subtitle matches:", file=sys.stderr)
    for i, result in enumerate(dual_results):
        print(f"  {i+1}. {result.get('movie_title', result.get('title', 'Unknown'))}", file=sys.stderr)
        print(f"     Languages: {result.get('languages', 'N/A')}", file=sys.stderr)
        print(f"     URL: {result.get('url', result.get('download_url', 'N/A'))}", file=sys.stderr)
        print()
    
    if dual_results:
        print(f"INFO Found {len(dual_results)} dual subtitle matches!", file=sys.stderr)
        print("INFO To download, run:", file=sys.stderr)
        print(f"  python tamil_subtitle_downloader.py {movie_title} {year} --download", file=sys.stderr)
    else:
        print("WARNING No dual subtitle matches found.", file=sys.stderr)
        print("\nSUGGESTION: Try downloading manually from:", file=sys.stderr)
        print("  - https://www.opensubtitles.com/", file=sys.stderr)
        print("  - https://subscene.com/", file=sys.stderr)
        print("  - https://www.addic7ed.com/", file=sys.stderr)


if __name__ == "__main__":
    main()
