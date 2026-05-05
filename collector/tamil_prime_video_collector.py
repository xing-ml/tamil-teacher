#!/usr/bin/env python3
"""Prime Video Tamil/English subtitle collector.

This module extracts Tamil and English subtitles from Prime Video using Playwright.
Requires user authentication (cookies or login credentials).
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional


def login_prime_video(
    email: str,
    password: str,
    headless: bool = False,
) -> dict:
    """Login to Prime Video and extract cookies.
    
    Args:
        email: Prime Video email
        password: Prime Video password
        headless: Run in headless mode
    
    Returns:
        dict with cookies and login status
    """
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            
            try:
                print("INFO Navigating to Prime Video...", file=sys.stderr)
                page.goto("https://www.primevideo.com", timeout=30000)
                time.sleep(5)
                
                # Find Join Prime button
                join_prime = page.query_selector('a:has-text("Join Prime")')
                if not join_prime:
                    print("WARNING Could not find Join Prime button", file=sys.stderr)
                    return {"success": False, "cookies": None}
                
                print("INFO Found Join Prime button", file=sys.stderr)
                join_prime.click()
                time.sleep(3)
                
                # Find email input
                email_input = page.query_selector('input[id="ap_email"]')
                if not email_input:
                    print("WARNING Could not find email input", file=sys.stderr)
                    return {"success": False, "cookies": None}
                
                email_input.fill(email)
                
                # Find continue button
                continue_btn = page.query_selector('input[id="continue"]')
                if not continue_btn:
                    print("WARNING Could not find continue button", file=sys.stderr)
                    return {"success": False, "cookies": None}
                
                continue_btn.click()
                time.sleep(3)
                
                # Find password input
                password_input = page.query_selector('input[id="ap_password"]')
                if not password_input:
                    print("WARNING Could not find password input", file=sys.stderr)
                    return {"success": False, "cookies": None}
                
                password_input.fill(password)
                
                # CHECK "Keep me signed in" BEFORE signing in
                keep_signed_in = page.query_selector('input[id="rememberMe"]')
                if keep_signed_in:
                    print("INFO Checking Keep me signed in checkbox", file=sys.stderr)
                    keep_signed_in.check()
                
                # Find sign in submit button
                sign_in_submit = page.query_selector('input[id="signInSubmit"]')
                if not sign_in_submit:
                    print("WARNING Could not find sign in submit button", file=sys.stderr)
                    return {"success": False, "cookies": None}
                
                sign_in_submit.click()
                time.sleep(5)
                
                cookies = context.cookies()
                print("INFO Login successful, cookies extracted", file=sys.stderr)
                return {"success": True, "cookies": cookies}
            
            finally:
                browser.close()
    
    except Exception as e:
        print(f"ERROR Login failed: {e}", file=sys.stderr)
        return {"success": False, "cookies": None}


def find_tamil_movies(cookies: list, headless: bool = False) -> list:
    """Navigate to Tamil movies page and extract movie URLs.
    
    Args:
        cookies: List of cookies for authentication
        headless: Run in headless mode
    
    Returns:
        List of movie URLs
    """
    movie_urls = []
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            context.add_cookies(cookies)
            page = context.new_page()
            
            try:
                print("INFO Navigating to Prime Video...", file=sys.stderr)
                page.goto("https://www.primevideo.com", timeout=30000)
                time.sleep(5)
                
                # Take screenshot for debugging
                page.screenshot(path="temp/prime_video_home.png")
                print("INFO Screenshot saved to temp/prime_video_home.png", file=sys.stderr)
                
                # List all clickable elements to find app launcher
                print("INFO Listing clickable elements...", file=sys.stderr)
                clickable = page.query_selector_all('button, a, [role="button"], [tabindex="0"]')
                for i, el in enumerate(clickable[:50]):
                    text = el.text_content().strip()
                    role = el.get_attribute('role')
                    aria_label = el.get_attribute('aria-label')
                    tag = el.evaluate('el => el.tagName')
                    if text or aria_label:
                        print(f"  [{i}] tag={tag} text={text[:50]} aria-label={aria_label} role={role}", file=sys.stderr)
                
                # Click on the app launcher icon (9 dots)
                print("INFO Looking for app launcher icon...", file=sys.stderr)
                app_launcher = page.query_selector('button[aria-label="Apps"]')
                if not app_launcher:
                    app_launcher = page.query_selector('div[role="button"]:has-text("Apps")')
                
                if not app_launcher:
                    print("WARNING Could not find app launcher icon", file=sys.stderr)
                    return movie_urls
                
                print("INFO Found app launcher icon, clicking...", file=sys.stderr)
                app_launcher.click()
                time.sleep(3)
                
                # Click on "Best of India"
                print("INFO Looking for Best of India...", file=sys.stderr)
                best_of_india = page.query_selector('a:has-text("Best of India")')
                if not best_of_india:
                    print("WARNING Could not find Best of India", file=sys.stderr)
                    return movie_urls
                
                print("INFO Found Best of India, clicking...", file=sys.stderr)
                best_of_india.click()
                time.sleep(5)
                
                # Scroll down to find "Movies in Tamil"
                print("INFO Scrolling down to find Movies in Tamil...", file=sys.stderr)
                page.mouse.wheel(0, 2000)
                time.sleep(3)
                
                # Click on "See more>" for "Movies in Tamil"
                print("INFO Looking for See more...", file=sys.stderr)
                see_more = page.query_selector('a:has-text("See more")')
                if not see_more:
                    print("WARNING Could not find See more", file=sys.stderr)
                    return movie_urls
                
                print("INFO Found See more, clicking...", file=sys.stderr)
                see_more.click()
                time.sleep(5)
                
                # Extract movie URLs
                print("INFO Extracting Tamil movie URLs...", file=sys.stderr)
                movie_links = page.query_selector_all('a[href*="/detail/"]')
                for link in movie_links:
                    href = link.get_attribute('href')
                    if href and '/detail/' in href:
                        movie_urls.append(f"https://www.primevideo.com{href}")
                
                print(f"INFO Found {len(movie_urls)} Tamil movie URLs", file=sys.stderr)
            
            finally:
                browser.close()
    
    except Exception as e:
        print(f"ERROR Navigation failed: {e}", file=sys.stderr)
    
    return movie_urls


def extract_prime_subtitles(
    video_url: str,
    cookies: list = None,
    headless: bool = True,
) -> dict:
    """Extract subtitles from a Prime Video video.
    
    Args:
        video_url: Prime Video video URL
        cookies: List of cookies for authentication
        headless: Run in headless mode
    
    Returns:
        dict with keys: 'tamil', 'english', 'has_dual_subtitles'
    """
    result = {
        'tamil': None,
        'english': None,
        'has_dual_subtitles': False,
        'error': None,
    }
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            
            if cookies:
                context.add_cookies(cookies)
            
            page = context.new_page()
            
            try:
                print(f"INFO Navigating to: {video_url}", file=sys.stderr)
                page.goto(video_url, timeout=30000)
                time.sleep(10)
                
                # Look for subtitle/caption button
                caption_selectors = [
                    '[data-test="cc-button"]',
                    '[data-testid="cc-button"]',
                    '[class*="cc-button"]',
                    '[class*="caption-button"]',
                    'button[aria-label*="Subtitle"]',
                    'button[aria-label*="Caption"]',
                ]
                
                caption_button = None
                for selector in caption_selectors:
                    try:
                        caption_button = page.wait_for_selector(selector, timeout=5000)
                        if caption_button:
                            print(f"INFO Found caption button with selector: {selector}", file=sys.stderr)
                            break
                    except:
                        continue
                
                if not caption_button:
                    result['error'] = "Could not find caption button"
                    return result
                
                caption_button.click()
                time.sleep(2)
                
                # Extract available subtitle languages
                subtitle_selectors = [
                    '[data-test="cc-option"]',
                    '[data-testid="cc-option"]',
                    '[class*="cc-option"]',
                    '[class*="subtitle-option"]',
                    '[class*="caption-option"]',
                ]
                
                subtitle_options = []
                for selector in subtitle_selectors:
                    try:
                        subtitle_options = page.query_selector_all(selector)
                        if subtitle_options:
                            print(f"INFO Found subtitle options with selector: {selector}", file=sys.stderr)
                            break
                    except:
                        continue
                
                subtitles = []
                for option in subtitle_options:
                    text = option.text_content().lower()
                    if 'tamil' in text:
                        subtitles.append('ta')
                    elif 'english' in text:
                        subtitles.append('en')
                
                print(f"INFO Available subtitles: {subtitles}", file=sys.stderr)
                
                if 'ta' in subtitles and 'en' in subtitles:
                    result['has_dual_subtitles'] = True
                    result['error'] = "Dual subtitles available but content extraction requires additional setup"
                else:
                    result['error'] = f"Only found subtitles: {subtitles}. Need both 'ta' and 'en'."
            
            finally:
                browser.close()
        
        return result
        
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        result['error'] = str(e)
        return result


def main():
    """Main function for testing Prime Video subtitle extraction."""
    if len(sys.argv) < 2:
        print("Usage: python tamil_prime_video_collector.py <prime_url> [email] [password]", file=sys.stderr)
        print("Example: python tamil_prime_video_collector.py https://www.primevideo.com/... your@email.com password", file=sys.stderr)
        sys.exit(1)
    
    video_url = sys.argv[1]
    email = sys.argv[2] if len(sys.argv) > 2 else None
    password = sys.argv[3] if len(sys.argv) > 3 else None
    
    email = email or "xing.c@hotmail.com"
    password = password or "789qweasd"
    
    # Login
    print("INFO Logging in...", file=sys.stderr)
    login_result = login_prime_video(email, password)
    if not login_result['success']:
        print("ERROR Login failed", file=sys.stderr)
        sys.exit(1)
    cookies = login_result['cookies']
    
    # If video URL is provided, extract subtitles
    if video_url and '/detail/' in video_url:
        result = extract_prime_subtitles(video_url, cookies)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Navigate to Tamil movies and extract URLs
        movie_urls = find_tamil_movies(cookies)
        print(f"INFO Tamil movie URLs: {json.dumps(movie_urls, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
