#!/usr/bin/env python3
"""Test script for TV show episode URL extraction.

Usage:
    python3 -m collector.test_tv_episodes
"""

import sys
import time
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collector.prime_subtitle_dl import (
    _check_login_status,
    login_prime_video,
)


def extract_episodes_from_page(page, show_url: str) -> dict:
    """Extract episode list and URLs from a TV show detail page.
    
    Args:
        page: Playwright page object
        show_url: TV show detail page URL
    
    Returns:
        Dict with 'episodes' list and 'episode_links' list
    """
    # Navigate to the show page
    print(f"INFO Navigating to: {show_url}", file=sys.stderr)
    page.goto(show_url, timeout=30000)
    page.wait_for_load_state('domcontentloaded')
    time.sleep(3)
    
    # Get page title
    page_title = page.evaluate('''() => document.title''')
    print(f"INFO Page title: {page_title}", file=sys.stderr)
    
    # Check for season selector
    season_links = page.evaluate('''() => {
        const links = [];
        const seasonLinks = document.querySelectorAll('a._1NNx6V');
        for(const link of seasonLinks) {
            const text = link.textContent?.trim();
            if(text && text.match(/Season\\s*\\d+/i)) {
                links.push({
                    text: text,
                    href: link.getAttribute('href'),
                });
            }
        }
        return links;
    }''')
    print(f"INFO Season links: {len(season_links)}", file=sys.stderr)
    for link in season_links:
        print(f"  - {link}", file=sys.stderr)
    
    # Extract episodes from page JSON
    episodes_json = page.evaluate('''() => {
        for(const script of document.querySelectorAll('script[type="application/json"]')) {
            try {
                const data = JSON.parse(script.innerHTML);
                const body = data?.init?.preparations?.body;
                if(body && body.atf && body.btf) {
                    const detail = body.btf?.state?.detail?.detail;
                    if(detail) {
                        const episodes = [];
                        for(const [id, det] of Object.entries(detail)) {
                            if(det.titleType === 'episode') {
                                episodes.push({
                                    id: id,
                                    title: det.title,
                                    seasonNumber: det.seasonNumber,
                                    episodeNumber: det.episodeNumber,
                                    titleID: det.titleID,
                                    hasPlayability: !!det.playabilityStatus,
                                    hasPlaybackEnvelope: !!det.playbackEnvelope,
                                    playbackEnvelope: det.playbackEnvelope ? 'present' : null,
                                });
                            }
                        }
                        return episodes;
                    }
                }
            } catch(e) {}
        }
        return null;
    }''')
    
    if episodes_json:
        print(f"INFO Episodes from JSON: {len(episodes_json)}", file=sys.stderr)
        for ep in episodes_json[:3]:
            print(f"  - {json.dumps(ep, indent=2, ensure_ascii=False)}", file=sys.stderr)
    
    # Check for episode list cards in DOM
    episode_links = page.evaluate('''() => {
        const links = [];
        
        // Try to find episode list cards
        const cards = document.querySelectorAll('[data-testid="episode-list-card"]');
        for(const card of cards) {
            const link = card.querySelector('a[href*="detail"]');
            if(link) {
                links.push({
                    href: link.getAttribute('href'),
                    text: link.textContent?.trim(),
                });
            }
        }
        
        // Try to find episode links in episode sections
        const sections = document.querySelectorAll('[data-testid*="episode"]');
        for(const section of sections) {
            const link = section.querySelector('a[href*="detail"]');
            if(link && !links.find(l => l.href === link.getAttribute('href'))) {
                links.push({
                    href: link.getAttribute('href'),
                    text: link.textContent?.trim(),
                });
            }
        }
        
        return links;
    }''')
    
    print(f"INFO Episode links from cards: {len(episode_links)}", file=sys.stderr)
    for link in episode_links[:20]:
        print(f"  - {link}", file=sys.stderr)
    
    # Check for all links with /detail/ in them
    all_detail_links = page.evaluate('''() => {
        const links = [];
        const allLinks = document.querySelectorAll('a[href*="detail"]');
        for(const link of allLinks) {
            const href = link.getAttribute('href');
            const text = link.textContent?.trim();
            if(href && href.includes('/detail/') && text && !text.match(/Season\\s*\\d+/i) && !text.match(/See more/i)) {
                links.push({
                    href: href,
                    text: text,
                });
            }
        }
        return links;
    }''')
    
    print(f"INFO All detail links: {len(all_detail_links)}", file=sys.stderr)
    for link in all_detail_links[:20]:
        print(f"  - {link}", file=sys.stderr)
    
    return {
        'page_title': page_title,
        'season_links': season_links,
        'episodes_json': episodes_json,
        'episode_links': episode_links,
        'all_detail_links': all_detail_links,
    }


def main():
    """Main function."""
    from playwright.sync_api import sync_playwright
    
    # TV show URL from user
    show_url = "https://www.primevideo.com/detail/0OJJ14MGOIWZG5O3S39NDD4C89/"
    
    # Prime Video credentials
    email = "xing.c@hotmail.com"
    password = "789qweasd"
    
    with sync_playwright() as p:
        # Launch browser with headless=False for manual login
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # Check login status
            print("INFO Checking login status...", file=sys.stderr)
            is_logged_in, has_join_prime = _check_login_status(page)
            print(f"INFO Login status: is_logged_in={is_logged_in}, has_join_prime={has_join_prime}", file=sys.stderr)
            
            if not is_logged_in:
                # Login
                print("INFO Logging in...", file=sys.stderr)
                login_result = login_prime_video(page, email, password)
                if not login_result['success']:
                    print("ERROR Login failed", file=sys.stderr)
                    return
            
            # Extract episodes
            print("\n" + "=" * 60, file=sys.stderr)
            print("INFO Extracting episodes...", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
            
            result = extract_episodes_from_page(page, show_url)
            
            print("\n" + "=" * 60, file=sys.stderr)
            print("INFO Summary:", file=sys.stderr)
            print(f"  Page title: {result['page_title']}", file=sys.stderr)
            print(f"  Season links: {len(result['season_links'])}", file=sys.stderr)
            print(f"  Episodes from JSON: {len(result['episodes_json']) if result['episodes_json'] else 0}", file=sys.stderr)
            print(f"  Episode links from cards: {len(result['episode_links'])}", file=sys.stderr)
            print(f"  All detail links: {len(result['all_detail_links'])}", file=sys.stderr)
            print("=" * 60, file=sys.stderr)
        
        finally:
            print("\nINFO Closing browser...", file=sys.stderr)
            browser.close()


if __name__ == "__main__":
    main()
