#!/usr/bin/env python3
"""Test fetching subtitles from known Tamil movies."""

from youtube_transcript_api import YouTubeTranscriptApi

tamil_movie_ids = [
    ("zTWmSqHCKA4", "Lock Up (Tamil movie)"),
    ("EnnMBmn__lo", "Aan Paavam (1985 Tamil comedy)"),
    ("zJ9buDm-xPU", "Mayamana Nizhal"),
]

for video_id, title in tamil_movie_ids:
    print(f"\n{'='*60}")
    print(f"Testing: {title}")
    print(f"Video ID: {video_id}")
    print('='*60)
    
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id, languages=["ta", "en"])
        
        text_items = []
        for item in transcript:
            if hasattr(item, 'text'):
                text_items.append(item.text)
        
        full_text = " ".join(text_items)
        print(f"✓ SUCCESS: Got {len(transcript)} transcript items")
        print(f"  Total text: {len(full_text)} characters")
        if text_items:
            print(f"  First 150 chars: {text_items[0][:150]}...")
        
    except Exception as e:
        print(f"✗ FAILED: {str(e)[:100]}")
