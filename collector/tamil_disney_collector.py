#!/usr/bin/env python3
"""Disney+ Tamil/English subtitle collector.

This module attempts to extract Tamil and English subtitles from Disney+ videos.
Note: Disney+ has DRM protection and requires authentication.
This script is for educational purposes only.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


def extract_disney_subtitles(
    video_url: str,
    output_dir: str = "temp",
    languages: list[str] = None,
) -> dict:
    """Extract subtitles from a Disney+ video.
    
    Args:
        video_url: Disney+ video URL
        output_dir: Directory to save subtitles
        languages: List of languages to extract (e.g., ['ta', 'en'])
    
    Returns:
        dict with keys: 'tamil', 'english', 'has_dual_subtitles'
    """
    if languages is None:
        languages = ['ta', 'en']
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    result = {
        'tamil': None,
        'english': None,
        'has_dual_subtitles': False,
        'error': None,
    }
    
    try:
        # Try to extract subtitles using yt-dlp
        # Note: This may not work due to Disney+ DRM
        # Use full path to yt-dlp
        yt_dlp_path = '/home/alumai/miniconda3/envs/tamil_teacher/bin/yt-dlp'
        
        cmd = [
            yt_dlp_path,
            '--dump-json',  # Just get metadata, don't download video
            '--sub-langs', ','.join(languages),
            '--skip-download',
            '--write-subs',
            '--sub-format', 'vtt',
            '--output', str(output_dir / '%(id)s.%(ext)s'),
            video_url,
        ]
        
        print(f"INFO Attempting to extract subtitles from: {video_url}", file=sys.stderr)
        print(f"INFO Languages: {languages}", file=sys.stderr)
        
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if proc.returncode != 0:
            print(f"WARNING yt-dlp failed: {proc.stderr}", file=sys.stderr)
            result['error'] = proc.stderr
            return result
        
        # Check for subtitle files
        for lang in languages:
            sub_file = output_dir / f"{video_url.split('/')[-1]}.{lang}.vtt"
            if sub_file.exists():
                content = sub_file.read_text(encoding='utf-8')
                # Parse VTT to get text
                text = parse_vtt(content)
                if text:
                    if lang == 'ta':
                        result['tamil'] = text
                    elif lang == 'en':
                        result['english'] = text
        
        # Check if we have both Tamil and English subtitles
        if result['tamil'] and result['english']:
            result['has_dual_subtitles'] = True
        
        return result
        
    except Exception as e:
        print(f"ERROR Failed to extract subtitles: {e}", file=sys.stderr)
        result['error'] = str(e)
        return result


def parse_vtt(vtt_content: str) -> str:
    """Parse VTT subtitle file to extract text."""
    lines = vtt_content.strip().split('\n')
    text_lines = []
    in_cue = False
    
    for line in lines:
        if line.startswith('WEBVTT'):
            continue
        if line.startswith('-->'):
            in_cue = True
            continue
        if in_cue and line.strip():
            text_lines.append(line.strip())
        elif not line.strip():
            in_cue = False
    
    return ' '.join(text_lines)


def main():
    """Main function for testing Disney+ subtitle extraction."""
    if len(sys.argv) < 2:
        print("Usage: python tamil_disney_collector.py <disney_url>", file=sys.stderr)
        sys.exit(1)
    
    video_url = sys.argv[1]
    result = extract_disney_subtitles(video_url)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
