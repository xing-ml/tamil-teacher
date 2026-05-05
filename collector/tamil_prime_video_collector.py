#!/usr/bin/env python3
"""Prime Video Tamil/English subtitle collector.

This module extracts Tamil and English subtitles from Prime Video using Playwright.
Requires user authentication (login credentials or cookies).
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional


def login_prime_video(
    email: str,
    password: str,
    headless: bool = True,
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
            # Setup browser
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            
            try:
                # Navigate to Prime Video login
                print("INFO Navigating to Prime Video login...", file=sys.stderr)
                page.goto("https://www.primevideo.com", timeout=30000)
                
                # Wait for login form
                time.sleep(5)
                
                # Find email input
                email_input = page.wait_for_selector('input[name="email"]', timeout=10000)
                email_input.fill(email)
                
                # Click continue
                page.wait_for_selector('input[type="submit"]', timeout=10000).click()
                
                # Wait for password form
                time.sleep(2)
                
                # Find password input
                password_input = page.wait_for_selector('input[type="password"]', timeout=10000)
                password_input.fill(password)
                
                # Click sign in
                page.wait_for_selector('input[type="submit"]', timeout=10000).click()
                
                # Wait for login to complete
                time.sleep(5)
                
                # Check if login was successful
                if "Sign in" in page.content() or "login" in page.content().lower():
                    print("WARNING Login may have failed", file=sys.stderr)
                    return {"success": False, "cookies": None}
                
                # Extract cookies
                cookies = context.cookies()
                print("INFO Login successful!", file=sys.stderr)
                return {"success": True, "cookies": cookies}
            
            finally:
                browser.close()
    
    except Exception as e:
        print(f"ERROR Login failed: {e}", file=sys.stderr)
        return {"success": False, "cookies": None}


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
            # Setup browser
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            
            # Add cookies if provided
            if cookies:
                context.add_cookies(cookies)
            
            page = context.new_page()
            
            try:
                # Navigate to video
                print(f"INFO Navigating to: {video_url}", file=sys.stderr)
                page.goto(video_url, timeout=30000)
                
                # Wait for video to load
                time.sleep(5)
                
                # Look for subtitle/caption button
                caption_button = page.wait_for_selector('[data-test="cc-button"]', timeout=10000)
                caption_button.click()
                
                # Wait for caption menu to appear
                time.sleep(2)
                
                # Extract available subtitle languages
                subtitle_options = page.query_selector_all('[data-test="cc-option"]')
                subtitles = []
                for option in subtitle_options:
                    text = option.text_content().lower()
                    if 'tamil' in text:
                        subtitles.append('ta')
                    elif 'english' in text:
                        subtitles.append('en')
                
                print(f"INFO Available subtitles: {subtitles}", file=sys.stderr)
                
                # If we have both Tamil and English, we can proceed
                if 'ta' in subtitles and 'en' in subtitles:
                    result['has_dual_subtitles'] = True
                    # Note: Extracting actual subtitle content is complex
                    # and may require additional steps
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
    
    if email and password:
        print("INFO Logging in...", file=sys.stderr)
        login_result = login_prime_video(email, password)
        if not login_result['success']:
            print("ERROR Login failed", file=sys.stderr)
            sys.exit(1)
        cookies = login_result['cookies']
    else:
        print("WARNING No login credentials provided. Using cookies instead.", file=sys.stderr)
        cookies = None
    
    result = extract_prime_subtitles(video_url, cookies)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
