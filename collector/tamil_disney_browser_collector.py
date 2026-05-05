#!/usr/bin/env python3
"""Disney+ subtitle collector using browser automation.

This script uses Selenium to automate browser interactions and extract subtitles
from Disney+ videos. Requires Chrome/Chromium browser.
"""

import json
import sys
import time
from pathlib import Path


def extract_disney_subtitles_browser(
    video_url: str,
    chromedriver_path: str = None,
) -> dict:
    """Extract subtitles from Disney+ using browser automation.
    
    Args:
        video_url: Disney+ video URL
        chromedriver_path: Path to ChromeDriver (optional)
    
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
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        
        # Setup Chrome options
        options = Options()
        options.add_argument('--headless')  # Run in headless mode
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        if chromedriver_path:
            service = Service(chromedriver_path)
        else:
            service = Service()
        
        driver = webdriver.Chrome(service=service, options=options)
        
        try:
            # Navigate to Disney+ video
            print(f"INFO Navigating to: {video_url}", file=sys.stderr)
            driver.get(video_url)
            
            # Wait for page to load
            time.sleep(5)
            
            # Look for subtitle/caption button
            caption_button = driver.find_element(By.CSS_SELECTOR, '[data-testid="caption-button"]')
            caption_button.click()
            
            # Wait for caption menu to appear
            time.sleep(2)
            
            # Extract available subtitle languages
            subtitle_options = driver.find_elements(By.CSS_SELECTOR, '[data-testid="subtitle-option"]')
            subtitles = []
            for option in subtitle_options:
                text = option.text.lower()
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
            driver.quit()
        
        return result
        
    except ImportError:
        print("ERROR: Selenium not installed. Install with: pip install selenium", file=sys.stderr)
        result['error'] = "Selenium not installed"
        return result
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        result['error'] = str(e)
        return result


def main():
    """Main function for testing Disney+ subtitle extraction."""
    if len(sys.argv) < 2:
        print("Usage: python tamil_disney_browser_collector.py <disney_url>", file=sys.stderr)
        sys.exit(1)
    
    video_url = sys.argv[1]
    result = extract_disney_subtitles_browser(video_url)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
