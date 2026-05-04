#!/usr/bin/env python3
"""Test YouTube API object structure."""

from youtube_transcript_api import YouTubeTranscriptApi

video_id = "dQw4w9WgXcQ"  # Famous video with transcripts

try:
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
    print(f"Type: {type(transcript)}")
    print(f"First item type: {type(transcript[0])}")
    print(f"First item: {transcript[0]}")
    print(f"First item dir: {dir(transcript[0])}")
except Exception as e:
    print(f"Error: {e}")
