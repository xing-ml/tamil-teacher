#!/usr/bin/env python3
"""
Direct YouTube transcript test - bypasses search, tests transcript fetching directly.
Tests if get_youtube_transcript() can fetch subtitles from known Tamil videos.
"""

import sys
from pathlib import Path

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    HAS_API = True
except ImportError:
    HAS_API = False
    print("ERROR: youtube-transcript-api not installed")
    sys.exit(1)

def get_youtube_transcript(video_id: str) -> str | None:
    """Get transcript for a YouTube video."""
    try:
        print(f"Fetching transcript for video ID: {video_id}", file=sys.stderr)
        # Use fetch() method - returns FetchedTranscript with FetchedTranscriptSnippet items
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["ta", "en"])
        chunks = []
        for item in transcript:
            # item is a FetchedTranscriptSnippet dataclass with .text attribute
            text = item.text.strip() if hasattr(item, 'text') else str(item).strip()
            if text:
                chunks.append(text)
        result = " ".join(chunks)
        print(f"SUCCESS: Got {len(transcript)} transcript items, {len(result)} characters", file=sys.stderr)
        return result
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return None

def main():
    """Test with known Tamil movie/content YouTube video IDs."""
    
    # Known Tamil YouTube videos (these are example IDs, may or may not be valid)
    # You can replace these with actual Tamil movie video IDs
    test_videos = [
        "dQw4w9WgXcQ",  # This is a famous video (test if API works at all)
        "jNQXAC9IVRw",  # Another famous video
    ]
    
    print("Testing YouTube transcript fetching...\n")
    print("NOTE: These are example IDs. For Tamil movies, you need actual video IDs.\n")
    
    for video_id in test_videos:
        print(f"\n{'='*60}")
        print(f"Testing video ID: {video_id}")
        print('='*60)
        transcript = get_youtube_transcript(video_id)
        if transcript:
            print(f"Transcript length: {len(transcript)} chars")
            print(f"First 200 chars: {transcript[:200]}\n")
        else:
            print("Failed to fetch transcript")

if __name__ == "__main__":
    main()
