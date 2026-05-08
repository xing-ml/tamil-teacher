#!/usr/bin/env python3
"""Test Prime Video login and navigate to Tamil movies with interactive selection."""

import json
import os
import sys
import time
import requests
from playwright.sync_api import sync_playwright

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

# ============================================================
# Log level switches
# ============================================================
DEBUG_MODE = False  # Set to True to see detailed debug output
INFO_MODE = True    # Set to False to suppress INFO messages


def _check_login_status(page) -> tuple:
    """检查是否已登录 Prime Video。
    
    Returns:
        (is_logged_in: bool, has_join_prime: bool)
        is_logged_in = True → 已登录，可跳过登录
        has_join_prime = True → 页面可见有 Join Prime 按钮，需要登录
        (False, False) → 页面加载失败，不确定状态
    """
    try:
        page.goto("https://www.primevideo.com", timeout=30000)
        page.wait_for_load_state('domcontentloaded')
        time.sleep(3)
        
        # 检查是否存在**可见的** "Join Prime" 按钮
        # 排除隐藏元素（footer链接、脚本文本等）
        has_join_prime = page.evaluate('''() => {
            const links = document.querySelectorAll('a');
            for (const link of links) {
                if (link.textContent.includes('Join Prime')) {
                    const style = window.getComputedStyle(link);
                    if (style.display !== 'none' && 
                        style.visibility !== 'hidden' && 
                        style.opacity !== '0' &&
                        link.offsetParent !== null) {
                        return true;
                    }
                }
            }
            return false;
        }''')
        return (not has_join_prime, has_join_prime)
    except Exception as e:
        print(f"WARNING _check_login_status failed: {e}", file=sys.stderr)
        return (False, False)  # 不确定状态，由 main() 决定


def login_prime_video(page, email: str, password: str) -> dict:
    """Login to Prime Video and extract cookies.
    
    Uses shared page object. Returns cookies for use by other functions.
    
    Args:
        page: Playwright page object (shared browser context)
        email: Prime Video email
        password: Prime Video password
    
    Returns:
        Dict with 'success' and 'cookies' keys
    """
    try:
        # Skip navigation if already on Prime Video (from _check_login_status)
        if 'primevideo.com' not in page.url:
            print("INFO Navigating to Prime Video...", file=sys.stderr)
            page.goto("https://www.primevideo.com", timeout=30000)
            time.sleep(5)
        else:
            print("INFO Already on Prime Video, skipping navigation", file=sys.stderr)
            time.sleep(2)
        
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
        time.sleep(8)
        
        # Verify login succeeded by checking page URL and content
        current_url = page.url
        print(f"INFO Post-login URL: {current_url}", file=sys.stderr)
        
        # Check if we're still on a login page (failed login)
        if 'amazon.com/ap/signin' in current_url or 'amazon.com/sign-in' in current_url:
            print("ERROR Login failed - still on Amazon signin page", file=sys.stderr)
            # Take screenshot for debugging
            try:
                page.screenshot(path='temp/login_failed.png')
                print("INFO Screenshot saved to temp/login_failed.png", file=sys.stderr)
            except Exception:
                pass
            return {"success": False, "cookies": None}
        
        # Check if login form still exists (login failed)
        remaining_form = page.query_selector('input[id="ap_password"]')
        if remaining_form:
            print("ERROR Login failed - password field still present", file=sys.stderr)
            try:
                page.screenshot(path='temp/login_failed.png')
                print("INFO Screenshot saved to temp/login_failed.png", file=sys.stderr)
            except Exception:
                pass
            return {"success": False, "cookies": None}
        
        # Verify we're on Prime Video homepage
        if 'primevideo.com' not in current_url:
            print(f"WARNING Unexpected URL after login: {current_url}", file=sys.stderr)
        
        cookies = page.context.cookies()
        print(f"INFO Login successful, {len(cookies)} cookies extracted", file=sys.stderr)
        return {"success": True, "cookies": cookies}
    
    except Exception as e:
        print(f"WARNING login_prime_video failed: {e}", file=sys.stderr)
        return {"success": False, "cookies": None}


def extract_categories_only(page, cookies: list) -> list:
    """Navigate to Prime Video homepage and extract only category names and hrefs.
    
    Uses shared page object. FAST - only extracts from homepage.
    
    Args:
        page: Playwright page object (shared browser context)
        cookies: Playwright cookies list
    
    Returns:
        List of category dicts: [{'name': '...', 'href': '...'}, ...]
    """
    try:
        # Already on Prime Video homepage after login / login check
        print("INFO Extracting categories from homepage...", file=sys.stderr)
        
        category_links_js = page.evaluate('''() => {
            const categories = [];
            const seen = new Set();
            const allLinks = document.querySelectorAll('a');
            for (const link of allLinks) {
                const href = link.getAttribute('href');
                if (!href) continue;
                // Exclude "See more" / "See More" navigation buttons
                const text = link.textContent.trim();
                if (!text || text.length <= 2 || text.length >= 100) continue;
                if (text.toLowerCase().includes('see more') || text.toLowerCase().includes('see\u200bmore')) continue;
                if (href.includes('/genre/') || href.includes('/collection/') || href.includes('/kids')) {
                    if (!seen.has(text)) {
                        seen.add(text);
                        categories.push({
                            name: text,
                            href: href.startsWith('http') ? href : 'https://www.primevideo.com' + href
                        });
                    }
                }
            }
            return categories;
        }''')
        
        print(f"INFO Found {len(category_links_js)} categories", file=sys.stderr)
        if DEBUG_MODE:
            for i, cat in enumerate(category_links_js):
                print(f"  {i+1}. {cat['name']}", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING extract_categories_only failed: {e}", file=sys.stderr)
        return []
    
    return category_links_js


def extract_sections_from_category(page, category_url: str, cookies: list) -> list:
    """Navigate to a category page and extract all sections with their URLs.
    
    Uses shared page object. Same JS logic as extract_category_tree.
    
    Args:
        page: Playwright page object (shared browser context)
        category_url: Category page URL
        cookies: Playwright cookies list
    
    Returns:
        List of section dicts: [{'name': '...', 'href': '...'}, ...]
    """
    try:
        print(f"INFO Navigating to category: {category_url[:80]}...", file=sys.stderr)
        page.goto(category_url, timeout=30000)
        page.wait_for_load_state('domcontentloaded')
        
        print("INFO   Scrolling to load all sections...", file=sys.stderr)
        for _scroll in range(3):
            page.evaluate('window.scrollBy(0, window.innerHeight)')
            time.sleep(2)
        
        # Use the EXACT same JS as extract_category_tree (proven working)
        # Container count debug (only when DEBUG_MODE is enabled)
        if DEBUG_MODE:
            container_count = page.evaluate('''() => {
                const allContainers = document.querySelectorAll("[class*='carousel'], [class*='cards'], [class*='card']");
                let count = 0;
                for (const c of allContainers) {
                    if (c.querySelectorAll("a[href*='/detail/']").length > 0) count++;
                }
                return count;
            }''')
            print(f"INFO   Debug: {container_count} containers with movie links", file=sys.stderr)
        
        sections_js = page.evaluate('''() => {
            const sections = [];
            const seen = new Set();
            const allContainers = document.querySelectorAll("[class*='carousel'], [class*='cards'], [class*='card']");
            
            for (const container of allContainers) {
                const movieLinks = container.querySelectorAll("a[href*='/detail/']");
                if (movieLinks.length === 0) continue;
                
                let title = "";
                let parent = container.parentElement;
                while (parent && !title) {
                    const titleEl = parent.querySelector('h2.headerComponents-qwttco');
                    if (titleEl) { title = titleEl.textContent.trim(); break; }
                    parent = parent.parentElement;
                    if (parent && parent.tagName === 'BODY') break;
                }
                if (!title || title.length < 2) continue;
                if (seen.has(title)) continue;
                seen.add(title);
                
                let seeMoreHref = null;
                // Try 1: direct "See more" links in container
                for (const link of container.querySelectorAll("a")) {
                    if (link.textContent.includes("See more") || link.textContent.includes("See More")) {
                        seeMoreHref = link.getAttribute("href");
                        break;
                    }
                }
                // Try 2: /browse/ link in parent
                if (!seeMoreHref) {
                    const par = container.parentElement;
                    if (par) {
                        for (const link of par.querySelectorAll("a")) {
                            const href = link.getAttribute("href");
                            if (href && href.includes("/browse/")) {
                                seeMoreHref = href.startsWith('http') ? href : 'https://www.primevideo.com' + href;
                                break;
                            }
                        }
                    }
                }
                
                let sectionHref = seeMoreHref;
                
                sections.push({ title: title, href: sectionHref });
            }
            
            // Return as JSON string to avoid serialization issues
            return JSON.stringify(sections);
        }''')
        
        # Parse JSON string back to Python list
        import json
        if isinstance(sections_js, str):
            try:
                sections_js = json.loads(sections_js)
                if not isinstance(sections_js, list):
                    sections_js = []
            except (json.JSONDecodeError, TypeError):
                print(f"WARNING JSON parse failed: {sections_js[:100]}", file=sys.stderr)
                sections_js = []
        else:
            print(f"WARNING sections_js is not a string: {type(sections_js)} = {sections_js}", file=sys.stderr)
            sections_js = []
        
        print(f"INFO   Found {len(sections_js)} sections", file=sys.stderr)
        for i, sec in enumerate(sections_js):
            print(f"    {i+1}. {sec.get('title', '?')} [NO URL]" if not sec.get('href') else f"    {i+1}. {sec.get('title', '?')}", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING extract_sections_from_category failed: {e}", file=sys.stderr)
        return []
    
    return sections_js


def extract_movie_subtitles(page, movie_url: str, movie_title: str = '', category: str = '', section: str = '',
                            _tv_show_dir: str = '', _tv_show_filename: str = '') -> dict:
    """Extract subtitles from a Prime Video movie or TV show episode using playback envelope API.
    
    Args:
        page: Playwright page object (shared browser context)
        movie_url: Movie/episode page URL
        movie_title: Title for display and filename
        category: Category name for directory structure
        section: Section name for directory structure
        _tv_show_dir: Override directory for TV show episodes (internal use)
        _tv_show_filename: Filename prefix for TV show episodes (internal use)
    
    Returns:
        Dict with keys: 'title', 'tamil', 'english', 'has_dual_subtitles',
            'subtitles_saved', 'subtitle_dir', 'error'
    """
    result = {
        'title': movie_title if movie_title else None,
        'tamil': None,
        'english': None,
        'has_dual_subtitles': False,
        'error': None,
        'subtitles_saved': 0,
        'subtitle_dir': '',
        'total_subtitle_types': 0,       # API returned count
        'filtered_subtitle_types': 0,    # After type filter
        'success_langs': [],             # Successful language codes
        'failed_langs': [],              # Failed language codes
        'ignored_subtitles': 0,          # Skipped because file already exists
        'ignored_reason': '',            # 'local_files_exist' or empty
    }
    
    def parse_vtt(content):
        """Parse VTT format and return list of captions."""
        lines = content.strip().split('\n')
        captions = []
        current_caption = {'start': '', 'end': '', 'text': ''}
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_caption['text']:
                    captions.append(current_caption.copy())
                    current_caption = {'start': '', 'end': '', 'text': ''}
                continue
            
            if '-->' in line:
                if current_caption['text']:
                    captions.append(current_caption.copy())
                parts = line.split('-->')
                current_caption = {
                    'start': parts[0].strip(),
                    'end': parts[1].strip(),
                    'text': ''
                }
            elif current_caption['start'] and current_caption['end']:
                if current_caption['text']:
                    current_caption['text'] += '\n' + line
                else:
                    current_caption['text'] = line
        
        if current_caption['text']:
            captions.append(current_caption)
        
        return captions
    
    def ttml2_to_srt(ttml_content):
        """Parse TTML2 XML content and convert to SRT format."""
        import xml.etree.ElementTree as ET
        
        # Define TTML namespaces
        namespaces = {
            'tts': 'http://www.w3.org/ns/ttml#styling',
            'tt': 'http://www.w3.org/ns/ttml',
            'ttm': 'http://www.w3.org/ns/ttml#metadata',
            'ttp': 'http://www.w3.org/ns/ttml#parameter'
        }
        
        try:
            root = ET.fromstring(ttml_content)
        except ET.ParseError:
            return None
        
        # Find all p (paragraph) elements
        paragraphs = root.findall('.//tt:p', namespaces)
        if not paragraphs:
            # Try without namespace
            paragraphs = root.findall('.//p')
        
        if not paragraphs:
            return None
        
        srt_lines = []
        index = 1
        
        for p_elem in paragraphs:
            # Get begin and end attributes
            begin = p_elem.get('begin', '')
            end = p_elem.get('end', '')
            
            # Get text content
            text_parts = []
            for child in p_elem:
                if child.text:
                    text_parts.append(child.text)
                if child.tail:
                    text_parts.append(child.tail)
            text = ' '.join(text_parts).strip()
            
            if not text or not begin or not end:
                continue
            
            # Convert time format from TTML (hh:mm:ss.mmm) to SRT (hh:mm:ss,mmm)
            def convert_time(time_str):
                # Handle TTML time format: hh:mm:ss.mmm or hh:mm:ss,mmm
                time_str = time_str.replace(',', '.')
                parts = time_str.split(':')
                if len(parts) == 3:
                    h, m, s = parts
                    ms = s.split('.')[1] if '.' in s else '000'
                    ms = ms.ljust(3, '0')[:3]
                    return f"{h}:{m}:{s.split('.')[0]},{ms}"
                return time_str
            
            srt_begin = convert_time(begin)
            srt_end = convert_time(end)
            
            srt_lines.append(f"{index}")
            srt_lines.append(f"{srt_begin} --> {srt_end}")
            srt_lines.append(text)
            srt_lines.append("")
            index += 1
        
        return '\n'.join(srt_lines) if srt_lines else None
    
    def fetch_subtitle(url):
        """Fetch subtitle file and parse TTML2 to SRT. Returns SRT string or None."""
        try:
            content = page.evaluate('''
                async (url) => {
                    try {
                        const resp = await fetch(url);
                        return await resp.text();
                    } catch(e) {
                        return null;
                    }
                }''', url)
            
            if not content:
                return None
            
            # Prime Video subtitles are always TTML2
            srt = ttml2_to_srt(content)
            if srt:
                caption_count = srt.count('\n\n')
                if DEBUG_MODE:
                    print(f"INFO Fetched subtitle (TTML2): {caption_count} captions from {url[:100]}", file=sys.stderr)
                return srt
            else:
                print(f"WARNING Failed to parse TTML2 content", file=sys.stderr)
                return None
        except Exception as e:
            print(f"WARNING Error fetching subtitle: {e}", file=sys.stderr)
        return None
    
    try:
        # Set up console logging AND response interception
        console_msgs = []
        webspa_responses = []  # Store responses from x-requested-with: WebSPA requests
        
        def on_console(msg):
            console_msgs.append(msg.text)
            if DEBUG_MODE:
                print(f"DEBUG Console: {msg.text}", file=sys.stderr)
        page.on('console', on_console)
        
        def on_response(response):
            url = response.url
            # Capture enrichItemMetadata response body
            if 'enrichItemMetadata' in url and response.status == 200:
                if DEBUG_MODE:
                    try:
                        body = response.text()
                        if body and len(body) > 10:
                            print(f"INFO enrichItemMetadata body (first 2000): {body[:2000]}", file=sys.stderr)
                    except Exception as e:
                        print(f"INFO Failed to get enrichItemMetadata body: {e}", file=sys.stderr)
        page.on('response', on_response)
        
        print(f"INFO Navigating to: {movie_url}", file=sys.stderr)
        page.goto(movie_url, timeout=30000)
        
        # Get movie title
        title_elem = page.query_selector('h1, [data-test="title"]')
        if title_elem:
            result['title'] = title_elem.text_content().strip()
            print(f"INFO Movie title: {result['title']}", file=sys.stderr)
        
        # Wait for video player to fully initialize (at least 15 seconds)
        print("INFO Waiting for video player to fully load (15s minimum)...", file=sys.stderr)
        for i in range(45):
            player_ready = page.evaluate('''() => {
                const video = document.querySelector('video');
                const playerContainer = document.querySelector('[data-testid="player-container"], [class*="player"]');
                return !!(video || playerContainer);
            }''')
            if player_ready:
                print(f"INFO Video player detected after {i+1}s, waiting for full initialization...", file=sys.stderr)
                break
            time.sleep(1)
        
        # Ensure we wait at least 15 seconds total
        elapsed = i + 1
        if elapsed < 15:
            print(f"INFO Waiting additional {15 - elapsed}s for player initialization...", file=sys.stderr)
            time.sleep(15 - elapsed)
        else:
            print(f"INFO Player already loaded, waiting extra 5s for network requests...", file=sys.stderr)
            time.sleep(5)
        
        # Extract props and envelope from page JSON, matching userscript's init() function
        if DEBUG_MODE:
            print("INFO Extracting props and envelope (matching userscript flow)...", file=sys.stderr)
        init_result = page.evaluate('''() => {
            const result = {error: null, envelope: null, actions: null};
            
            // Step 1: Extract props from page JSON (matching extractProps function)
            let props = undefined;
            for(const script of document.querySelectorAll('script[type="application/json"]')) {
                try {
                    const data = JSON.parse(script.innerHTML);
                    // New structure: data.init.preparations.body has atf/btf directly
                    if(data && data.init && data.init.preparations && data.init.preparations.body) {
                        const body = data.init.preparations.body;
                        if(body.atf && body.btf) {
                            props = body;
                            break;
                        }
                    }
                } catch(e) {}
            }
            
            if(!props) {
                result.error = "Could not extract props from page JSON";
                return result;
            }
            
            // Step 2: Extract actions from atf and btf (matching parseActions function)
            const actions = [];
            
            // Process atf actions
            const atfActions = props.atf.state.action.atf;
            if(atfActions) {
                for(const [id, action] of Object.entries(atfActions)) {
                    const extracted = action.primaryActions || action.playbackActions;
                    if(extracted) {
                        actions.push({id, source: 'atf', extracted});
                    }
                }
            }
            
            // Process btf actions
            const btfActions = props.btf.state.action.btf;
            if(btfActions) {
                for(const [id, action] of Object.entries(btfActions)) {
                    const extracted = action.primaryActions || action.playbackActions;
                    if(extracted) {
                        actions.push({id, source: 'btf', extracted});
                    }
                }
            }
            
            // Step 3: Find playbackEnvelope in primaryActions (matching parseActions function)
            for(const {id, source, extracted} of actions) {
                if(typeof extracted !== 'object' || !Array.isArray(extracted)) continue;
                
                for(const action of extracted) {
                    // New structure: primaryActions[].payload.playback.playbackEnvelope
                    if(action.payload && action.payload.playback && action.payload.playback.playbackEnvelope) {
                        result.envelope = action.payload.playback.playbackEnvelope;
                        result.expiry = action.payload.playback.expiryTime;
                        result.envelopeId = id;
                        result.envelopeSource = `${source}.${id}`;
                        break;
                    }
                }
                if(result.envelope) break;
            }
            
            // If envelope not found in actions, try old structure
            if(!result.envelope) {
                for(const {id, source, extracted} of actions) {
                    if(typeof extracted !== 'object' || !extracted.main || !extracted.main.children) continue;
                    for(const child of extracted.main.children) {
                        if(typeof child.playbackEnvelope !== 'undefined') {
                            result.envelope = child.playbackEnvelope;
                            result.expiry = child.expiryTime;
                            result.envelopeId = id;
                            result.envelopeSource = `${source}.${id}`;
                            break;
                        }
                    }
                    if(result.envelope) break;
                }
            }
            
            // Fallback: recursively search all nested objects for playbackEnvelope
            // This handles headless mode where structure is different (EXPAND_CARD_OPTION, etc.)
            if(!result.envelope) {
                const found = findPlaybackEnvelopeRecursive(actions);
                if(found) {
                    result.envelope = found.envelope;
                    result.expiry = found.expiry;
                    result.envelopeId = found.id;
                    result.envelopeSource = found.source;
                }
            }
            
            // Helper: recursively search for playbackEnvelope in any nested structure
            function findPlaybackEnvelopeRecursive(items, path = '') {
                for(const item of items) {
                    if(typeof item !== 'object' || item === null) continue;
                    
                    // Check direct property
                    if(item.playbackEnvelope) {
                        return { envelope: item.playbackEnvelope, expiry: item.expiryTime, id: item.id || 'unknown', source: item.source || 'unknown' };
                    }
                    
                    // Check nested payload
                    if(item.payload && typeof item.payload === 'object') {
                        // Direct playback.playbackEnvelope
                        if(item.payload.playback && item.payload.playback.playbackEnvelope) {
                            return { envelope: item.payload.playback.playbackEnvelope, expiry: item.payload.playback.expiryTime, id: item.id || 'unknown', source: item.source || 'unknown' };
                        }
                        // expandingCard.actions
                        if(item.payload.expandingCard && item.payload.expandingCard.actions) {
                            const found = findPlaybackEnvelopeRecursive(item.payload.expandingCard.actions, path + '.expandingCard.actions');
                            if(found) return found;
                        }
                        // Any other nested object
                        const found = findPlaybackEnvelopeRecursive([item.payload], path + '.payload');
                        if(found) return found;
                    }
                    
                    // Check actions array
                    if(item.actions && Array.isArray(item.actions)) {
                        const found = findPlaybackEnvelopeRecursive(item.actions, path + '.actions');
                        if(found) return found;
                    }
                    
                    // Check children
                    if(item.children && Array.isArray(item.children)) {
                        const found = findPlaybackEnvelopeRecursive(item.children, path + '.children');
                        if(found) return found;
                    }
                    
                    // Recurse into any other object properties
                    for(const key of Object.keys(item)) {
                        if(key === 'payload' || key === 'actions' || key === 'children') continue; // already handled
                        const val = item[key];
                        if(typeof val === 'object' && val !== null && !Array.isArray(val)) {
                            const found = findPlaybackEnvelopeRecursive([val], path + '.' + key);
                            if(found) return found;
                        } else if(Array.isArray(val)) {
                            const found = findPlaybackEnvelopeRecursive(val, path + '.' + key);
                            if(found) return found;
                        }
                    }
                }
                return null;
            }
            
            if(!result.envelope) {
                result.error = "Could not find playbackEnvelope in actions";
                result.actions = actions.map(a => ({
                    id: a.id,
                    source: a.source,
                    hasPrimaryActions: !!a.extracted.primaryActions,
                    hasPlaybackActions: !!a.extracted.playbackActions,
                    primaryActionsCount: a.extracted.primaryActions?.length || 0,
                    // Full extracted structure for debugging
                    extractedKeys: Object.keys(a.extracted || {}),
                    extractedPreview: JSON.stringify(a.extracted).substring(0, 2000),
                    extractedFull: JSON.stringify(a.extracted)
                }));
                return result;
            }
            
            // Step 4: Return envelope info for POST request
            result.movieUrl = window.location.href;
            result.pageTitleId = props.btf.state.pageTitleId;
            
            return result;
        }''')
        
        if init_result.get('error'):
            print(f"WARNING {init_result['error']}", file=sys.stderr)
            # Debug: print actions structure
            if 'actions' in init_result and init_result['actions']:
                print(f"DEBUG Actions found: {len(init_result['actions'])}", file=sys.stderr)
                for i, action in enumerate(init_result['actions']):
                    print(f"  Action {i}: id={action.get('id')}, source={action.get('source')}, "
                          f"primaryActions={action.get('hasPrimaryActions')}, "
                          f"playbackActions={action.get('hasPlaybackActions')}, "
                          f"keys={action.get('extractedKeys')}", file=sys.stderr)
                    preview = action.get('extractedPreview', '')
                    if preview and len(preview) > 200:
                        preview = preview[:200] + '...'
                    if preview:
                        print(f"    preview: {preview}", file=sys.stderr)
            # Debug: print current page URL and title
            print(f"DEBUG Current page URL: {page.url}", file=sys.stderr)
            print(f"DEBUG Current page title: {page.title()}", file=sys.stderr)
            # Take screenshot for debugging
            try:
                page.screenshot(path='temp/movie_page_failed.png')
                print(f"INFO Screenshot saved to temp/movie_page_failed.png", file=sys.stderr)
            except Exception as ss_err:
                print(f"WARNING Screenshot failed: {ss_err}", file=sys.stderr)
            result['error'] = init_result['error']
            return result
        
        envelope = init_result['envelope']
        envelope_source = init_result['envelopeSource']
        movie_url = init_result['movieUrl']
        
        if DEBUG_MODE:
            print(f"INFO Found playbackEnvelope from {envelope_source}", file=sys.stderr)
            print(f"INFO Envelope preview: {envelope[:100] if isinstance(envelope, str) else 'not a string'}...", file=sys.stderr)
        print(f"INFO Movie URL: {movie_url}", file=sys.stderr)
        
        # Step 5: POST to GetVodPlaybackResources with timedTextUrlsRequest
        # Use hardcoded device params (same as the page uses)
        if DEBUG_MODE:
            print("INFO Trying GetVodPlaybackResources with timedTextUrlsRequest...", file=sys.stderr)
        
        # Get deviceID from the page's own GetVodPlaybackResources requests
        # We'll extract it from the URL by looking at the page's state
        device_id = page.evaluate('''() => {
            // Try to find deviceID from the page's state
            const body = document.querySelector('script[type="application/json"]');
            if(!body) return 'default-device-id';
            try {
                const data = JSON.parse(body.innerHTML);
                // Check atf.state.globalParameters
                const gp = data?.init?.preparations?.body?.atf?.state?.globalParameters;
                if(gp && gp.deviceID) return gp.deviceID;
                // Check btf.state
                const btf = data?.init?.preparations?.body?.btf?.state;
                if(btf && btf.deviceID) return btf.deviceID;
                return 'default-device-id';
            } catch(e) {
                return 'default-device-id';
            }
        }''')
        
        device_params = {
            'deviceID': device_id,
            'deviceTypeID': 'AOAGZA014O5RE',
            'marketplaceID': 'A15PK738MTQHSO',
            'uxLocale': 'en_US'
        }
        if DEBUG_MODE:
            print(f"INFO Device params: {device_params}", file=sys.stderr)
        
        sub_info_result = page.evaluate(
            '''async ({ envelope, deviceParams, movieUrl, debugMode }) => {
                try {
                    // Try POST to GetVodPlaybackResources endpoint with timedTextUrlsRequest
                    const baseUrl = 'https://atv-ps-fe.primevideo.com/playback/prs/GetVodPlaybackResources';
                    const url = baseUrl + '?' + new URLSearchParams({
                        deviceID: deviceParams.deviceID,
                        deviceTypeID: deviceParams.deviceTypeID,
                        gascEnabled: 'true',
                        marketplaceID: deviceParams.marketplaceID,
                        uxLocale: deviceParams.uxLocale,
                        firmware: '1',
                        titleId: ''
                    });
                    
                    if (debugMode) {
                        console.log('DEBUG GVod URL:', url);
                    }
                    
                    const response = await fetch(url, {
                        credentials: 'include',
                        method: 'POST',
                        mode: 'cors',
                        headers: {
                            'Content-Type': 'application/json',
                            'x-requested-with': 'WebSPA',
                            'Referer': movieUrl
                        },
                        body: JSON.stringify({
                            globalParameters: {
                                deviceCapabilityFamily: 'WebPlayer',
                                playbackEnvelope: envelope
                            },
                            timedTextUrlsRequest: {
                                supportedTimedTextFormats: ['TTMLv2', 'DFXP']
                            }
                        })
                    });
                    
                    const contentType = response.headers.get('content-type') || '';
                    const text = await response.text();
                    
                    if (debugMode) {
                        console.log('DEBUG GVod status:', response.status);
                        console.log('DEBUG GVod contentType:', contentType);
                        console.log('DEBUG GVod body (first 2000):', text.substring(0, 2000));
                    }
                    
                    let parsed = null;
                    if(contentType.includes('application/json')) {
                        try {
                            parsed = JSON.parse(text);
                            if (debugMode) {
                                console.log('DEBUG GVod parsed timedTextUrls:', JSON.stringify(parsed.timedTextUrls, null, 2).substring(0, 2000));
                            }
                        } catch(e) {
                            if (debugMode) {
                                console.log('DEBUG GVod JSON parse error:', e.message);
                            }
                        }
                    }
                    
                    return {
                        status: response.status,
                        contentType: contentType,
                        bodyPreview: text.substring(0, 3000),
                        parsed: parsed
                    };
                } catch(e) {
                    if (debugMode) {
                        console.log('DEBUG GVod error:', e.message);
                        console.log('DEBUG GVod error stack:', e.stack);
                    }
                    return { error: e.message || String(e) };
                }
            }''',
            {'envelope': envelope, 'deviceParams': device_params, 'movieUrl': movie_url, 'debugMode': DEBUG_MODE}
        )
        
        if DEBUG_MODE:
            print(f"INFO Subtitle API result: status={sub_info_result.get('status')}, contentType={sub_info_result.get('contentType')}", file=sys.stderr)
        
        if sub_info_result.get('parsed'):
            parsed = sub_info_result['parsed']
            # Check for timedTextUrls.result (matching userscript's getSubInfo return)
            timed_text_urls = None
            if parsed.get('timedTextUrls') and parsed['timedTextUrls'].get('result'):
                timed_text_urls = parsed['timedTextUrls']['result']
                subtitle_urls = timed_text_urls.get('subtitleUrls', [])
                result['total_subtitle_types'] = len(subtitle_urls)
                if DEBUG_MODE:
                    print(f"INFO Found {len(subtitle_urls)} subtitle entries in timedTextUrls.result.subtitleUrls", file=sys.stderr)
                for sub in subtitle_urls:
                    lang = sub.get('languageCode', 'unknown')
                    url = sub.get('url', 'no url')
                    sub_type = sub.get('type', 'Subtitle')
                    print(f"  - {lang} ({sub_type}): {url[:100]}...", file=sys.stderr)
            elif parsed.get('globalError'):
                print(f"WARNING Global error: {parsed['globalError']}", file=sys.stderr)
            else:
                print(f"INFO Parsed response (first 500): {json.dumps(parsed, ensure_ascii=False)[:500]}", file=sys.stderr)
        else:
            print(f"INFO Body preview: {sub_info_result.get('bodyPreview', '')[:500]}", file=sys.stderr)
            result['error'] = "No valid subtitle data returned"
            result['total_subtitle_types'] = 0
            result['filtered_subtitle_types'] = 0
            result['success_langs'] = []
            result['failed_langs'] = []
            return result
        
        # ========================
        # Collect ALL subtitles per Tampermonkey naming convention
        # ========================
        # Allowed types: only Subtitle (non-CC) and Sdh (CC)
        # Exclude: SubtitleMachineGenerated, ForcedNarrative, etc.
        ALLOWED_TYPES = {'Subtitle', 'Sdh'}
        
        def build_filename(movie_name, lang_code, subtitle_type):
            """Build filename following Tampermonkey naming convention.
            
            Convention:
              filename.languageCode          -> Subtitle (non-CC)
              filename.languageCode[cc]     -> Sdh (CC)
            """
            safe_name = movie_name.replace('/', '_').replace('\\', '_').replace(':', '.')
            name = f"{safe_name}.{lang_code}"
            
            if subtitle_type == 'Sdh':
                name += '[cc]'
            
            return name
        
        # Filter subtitles: only allowed types (NO language filter - download ALL)
        filtered_subtitles = []
        for sub in subtitle_urls:
            sub_type = sub.get('type', 'Subtitle')
            lang_code = sub.get('languageCode', 'unknown')
            url = sub.get('url', '')
            
            if sub_type not in ALLOWED_TYPES:
                continue
            
            # Generate unique identifier: lang_code or lang_code[cc] for SDH
            if sub_type == 'Sdh':
                unique_id = f"{lang_code}[cc]"
            else:
                unique_id = lang_code
            
            filtered_subtitles.append({
                'lang_code': lang_code,
                'type': sub_type,
                'unique_id': unique_id,
                'url': url,
            })
        
        result['filtered_subtitle_types'] = len(filtered_subtitles)
        if DEBUG_MODE:
            print(f"INFO Filtered to {len(filtered_subtitles)} subtitles (types={ALLOWED_TYPES})", file=sys.stderr)
        
        if not filtered_subtitles:
            print(f"WARNING No target subtitles found for {result.get('title', 'unknown movie')}", file=sys.stderr)
            result['error'] = "No matching subtitles found (all filtered out by type)"
            result['success_langs'] = []
            result['failed_langs'] = []
            return result
        
        # Download and save each subtitle
        import os
        
        # Use movie_title parameter if available, otherwise fall back to page title
        safe_movie = (movie_title if movie_title else result.get('title') or 'movie').replace('/', '_').replace('\\', '_').replace(':', '.')
        
        # TV show override: use provided directory and filename prefix
        if _tv_show_dir:
            output_dir = _tv_show_dir
        else:
            # New directory structure: data/subtitles/{category}/{section}/{movie}/
            safe_cat = category.replace('/', '_').replace('\\', '_').replace(':', '.') if category else 'unknown'
            safe_sec = section.replace('/', '_').replace('\\', '_').replace(':', '.') if section else 'unknown'
            output_dir = os.path.join('data', 'subtitles', safe_cat, safe_sec, safe_movie)
        os.makedirs(output_dir, exist_ok=True)
        
        saved_count = 0
        downloaded_langs = set()
        failed_langs = []
        
        for sub in filtered_subtitles:
            lang_code = sub['lang_code']
            unique_id = sub['unique_id']  # e.g., 'en-us' or 'en-us[cc]'
            
            # Build filepath and check if file already exists
            # For TV shows, use _tv_show_filename instead of safe_movie
            name_base = _tv_show_filename if _tv_show_filename else safe_movie
            filename = build_filename(name_base, lang_code, sub['type'])
            filepath = os.path.join(output_dir, f"{filename}.srt")
            
            if os.path.exists(filepath):
                # File already exists, skip download
                if DEBUG_MODE:
                    print(f"INFO Skipped (exists): {filepath}", file=sys.stderr)
                saved_count += 1
                downloaded_langs.add(unique_id)
                result['ignored_subtitles'] += 1
                continue
            
            srt_content = None
            
            # Retry mechanism: 3s wait, max 3 retries
            max_retries = 3
            for attempt in range(max_retries):
                srt_content = fetch_subtitle(sub['url'])
                if srt_content:
                    break
                if attempt < max_retries - 1:
                    print(f"WARNING Retry {attempt+1}/{max_retries-1} for {unique_id} subtitle...", file=sys.stderr)
                    time.sleep(3)
            
            if not srt_content:
                print(f"WARNING Failed to fetch subtitle after {max_retries} attempts: {unique_id} ({sub['type']})", file=sys.stderr)
                failed_langs.append(unique_id)
                continue
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            caption_count = srt_content.count('\n\n')
            if DEBUG_MODE:
                print(f"INFO Saved: {filepath} ({caption_count} captions, type={sub['type']})", file=sys.stderr)
            saved_count += 1
            downloaded_langs.add(unique_id)
        
        # Update result with actual download status
        result['subtitles_saved'] = saved_count
        result['subtitle_dir'] = output_dir
        result['success_langs'] = sorted(downloaded_langs)
        result['failed_langs'] = failed_langs
        # Language codes are like 'ta-in', 'en-us', 'kn-in', etc. (may have [cc] suffix)
        has_tamil = any(lang.startswith('ta') for lang in downloaded_langs)
        has_english = any(lang.startswith('en') for lang in downloaded_langs)
        result['tamil'] = has_tamil
        result['english'] = has_english
        result['has_dual_subtitles'] = has_tamil and has_english
        if DEBUG_MODE:
            print(f"INFO Total subtitles saved: {saved_count} to {output_dir}", file=sys.stderr)
            print(f"INFO Languages: tamil={result['tamil']}, english={result['english']}, dual={result['has_dual_subtitles']}, langs={downloaded_langs}", file=sys.stderr)
        
        # Per-movie summary (always printed)
        error = result.get('error')
        ignored = result.get('ignored_subtitles', 0)
        if error:
            print(f"{result.get('title', 'unknown')}: 失败 - {error}", file=sys.stderr)
        else:
            success_count_movie = len(downloaded_langs)
            failed_count_movie = len(failed_langs)
            success_str = f"成功{success_count_movie}个" if downloaded_langs else "成功0个"
            failed_str = f"失败{failed_count_movie}个({', '.join(sorted(failed_langs))})" if failed_langs else "失败0个"
            ignored_str = f"忽略{ignored}个（已存在）" if ignored > 0 else ""
            parts = [f"{result.get('title', 'unknown')}: {result['total_subtitle_types']}种字幕 → 筛选后{result['filtered_subtitle_types']}种 ({', '.join(sorted(downloaded_langs))}) → {success_str}, {failed_str}"]
            if ignored_str:
                parts.append(ignored_str)
            print(" → ".join(parts), file=sys.stderr)
    
    except Exception as e:
        print(f"ERROR extract_movie_subtitles failed: {e}", file=sys.stderr)
        result['error'] = str(e)
        result['total_subtitle_types'] = 0
        result['filtered_subtitle_types'] = 0
        result['success_langs'] = []
        result['failed_langs'] = []
        return result
    
    return result

def fetch_section_movies(page, section_url: str, cookies: list) -> list:
    """Navigate to section page, scroll to collect all movies/TV shows.
    
    Uses shared page object. Only collects URLs and titles - type detection
    is deferred to download phase to avoid unnecessary navigation.
    
    Args:
        page: Playwright page object (shared browser context)
        section_url: The 'See more' URL for the section
        cookies: Playwright cookies list
    
    Returns:
        List of item dicts: {'title': '...', 'url': '...', 'type': 'movie'}
        (type is always 'movie' here; actual type detected during download)
    """
    # JS: extract movie/show cards from section page
    extract_js = '''() => {
        const items = [];
        for (const link of document.querySelectorAll("a[href*='/detail/']")) {
            const href = link.getAttribute("href");
            if (!href) continue;
            const url = href.startsWith('http') ? href : 'https://www.primevideo.com' + href;
            const title = link.textContent?.trim() || "";
            if (title && title.length > 2 && title.length < 100) {
                items.push({ url, title });
            }
        }
        return items;
    }'''
    
    seen_urls = {}
    
    try:
        # Handle relative URLs
        if section_url.startswith('/'):
            full_url = 'https://www.primevideo.com' + section_url
        elif section_url.startswith('http'):
            full_url = section_url
        else:
            full_url = 'https://www.primevideo.com' + '/' + section_url
        
        print(f"INFO Navigating to section: {full_url[:100]}...", file=sys.stderr)
        page.goto(full_url, timeout=30000)
        page.wait_for_load_state('domcontentloaded')
        
        # Scroll and accumulate cards from DOM
        consecutive_no_new = 0
        scroll_count = 0
        
        while scroll_count < 15:
            page.evaluate('window.scrollBy(0, 500)')
            time.sleep(2)
            
            current_items = page.evaluate(extract_js)
            new_count = 0
            for it in current_items:
                if it['url'] not in seen_urls:
                    seen_urls[it['url']] = it['title']
                    new_count += 1
            
            total = len(seen_urls)
            if new_count > 0:
                if INFO_MODE:
                    print(f"INFO Scroll #{scroll_count + 1}: {total} items total, {new_count} new", file=sys.stderr)
                consecutive_no_new = 0
            else:
                consecutive_no_new += 1
                if INFO_MODE:
                    print(f"INFO Scroll #{scroll_count + 1}: {total} items total, no new (streak: {consecutive_no_new})", file=sys.stderr)
            
            scroll_count += 1
            if consecutive_no_new >= 3:
                if INFO_MODE:
                    print(f"INFO Stable for 3 scrolls at {total} items - stopping", file=sys.stderr)
                break
        
        # Build result list (no type detection here - deferred to download phase)
        all_items = [{'title': title, 'url': url, 'type': 'movie'} for url, title in seen_urls.items()]
        if INFO_MODE:
            print(f"INFO Total items collected: {len(all_items)}", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING fetch_section_movies failed: {e}", file=sys.stderr)
        return []
    
    return all_items


def _extract_tv_show_episodes(page, show_url: str) -> list:
    """Extract episode list from a TV show detail page.
    
    Uses page JSON to get initial episodes, then scrolls to load more via API interception.
    
    Args:
        page: Playwright page object
        show_url: TV show detail page URL
    
    Returns:
        List of episode dicts: [{'title': '...', 'url': '...', 'season': N, 'episode': N}, ...]
    """
    episodes = []
    seen_ep_urls = set()
    
    try:
        # Set up API response interception for enrichItemMetadata
        api_episodes = []
        
        def on_response(response):
            url = response.url
            if 'enrichItemMetadata' in url and response.status == 200:
                try:
                    body = response.json()
                    if body.get('entities'):
                        for entity in body['entities']:
                            if entity.get('titleID') and entity.get('detail'):
                                det = entity['detail']
                                if det.get('titleType') == 'episode':
                                    ep_url = det.get('titleID', '')
                                    if ep_url and ep_url not in seen_ep_urls:
                                        seen_ep_urls.add(ep_url)
                                        api_episodes.append({
                                            'title': det.get('title', ''),
                                            'url': f"/detail/{ep_url}/",
                                            'season': det.get('seasonNumber', 0),
                                            'episode': det.get('episodeNumber', 0),
                                        })
                except Exception:
                    pass
        
        page.on('response', on_response)
        
        # Extract initial episodes from page JSON
        initial_episodes = page.evaluate('''() => {
            const episodes = [];
            for(const script of document.querySelectorAll('script[type="application/json"]')) {
                try {
                    const data = JSON.parse(script.innerHTML);
                    const body = data?.init?.preparations?.body;
                    if(body && body.atf && body.btf) {
                        const detail = body.btf?.state?.detail?.detail;
                        if(detail) {
                            for(const [id, det] of Object.entries(detail)) {
                                if(det.titleType === 'episode') {
                                    episodes.push({
                                        title: det.title || '',
                                        season: det.seasonNumber || 0,
                                        episode: det.episodeNumber || 0,
                                    });
                                }
                            }
                        }
                    }
                } catch(e) {}
            }
            return episodes;
        }''')
        
        for ep in initial_episodes:
            # Handle missing seasonNumber (default to 1)
            season = ep.get('season') or 1
            if ep['title'] and season > 0:
                episodes.append({
                    'title': ep['title'],
                    'season': season,
                    'episode': ep.get('episode', 0),
                })
        
        if not episodes:
            return []
        
        # Check if there are more episodes to load
        total_ep_count = page.evaluate('''() => {
            for(const script of document.querySelectorAll('script[type="application/json"]')) {
                try {
                    const data = JSON.parse(script.innerHTML);
                    const body = data?.init?.preparations?.body;
                    if(body && body.atf && body.btf) {
                        const epList = body.btf?.state?.episodeList;
                        if(epList) {
                            return epList.totalCardSize || 0;
                        }
                    }
                } catch(e) {}
            }
            return 0;
        }''')
        
        if total_ep_count > len(episodes):
            if INFO_MODE:
                print(f"INFO TV show has {total_ep_count} episodes, loading more...", file=sys.stderr)
            
            # Scroll to load more episodes (with timeout protection)
            max_scroll_time = 60  # seconds
            scroll_start = time.time()
            prev_count = len(episodes)
            
            while time.time() - scroll_start < max_scroll_time:
                # Scroll to pagination marker
                scroll_result = page.evaluate('''() => {
                    const marker = document.querySelector('[data-testid="dp-episode-list-pagination-marker"]');
                    if(marker) {
                        marker.scrollIntoView({behavior: 'instant'});
                        return true;
                    }
                    // Fallback: scroll to bottom
                    window.scrollTo(0, document.body.scrollHeight);
                    return true;
                }''')
                
                if not scroll_result:
                    break
                
                time.sleep(3)  # Wait for API call and DOM update
                
                # Check for new episodes from API interception
                new_from_api = len(api_episodes) - prev_count
                if new_from_api > 0:
                    for ep in api_episodes[prev_count:]:
                        episodes.append(ep)
                    prev_count = len(api_episodes)
                
                # Also check page JSON for new episodes
                current_ep_count = page.evaluate('''() => {
                    let count = 0;
                    for(const script of document.querySelectorAll('script[type="application/json"]')) {
                        try {
                            const data = JSON.parse(script.innerHTML);
                            const body = data?.init?.preparations?.body;
                            if(body && body.atf && body.btf) {
                                const detail = body.btf?.state?.detail?.detail;
                                if(detail) {
                                    for(const [id, det] of Object.entries(detail)) {
                                        if(det.titleType === 'episode') count++;
                                    }
                                }
                            }
                        } catch(e) {}
                    }
                    return count;
                }''')
                
                if current_ep_count >= total_ep_count:
                    if INFO_MODE:
                        print(f"INFO Loaded all {total_ep_count} episodes", file=sys.stderr)
                    break
                
                if INFO_MODE:
                    print(f"INFO Loaded {current_ep_count}/{total_ep_count} episodes", file=sys.stderr)
            
            # Add any remaining API episodes
            for ep in api_episodes[len(episodes):]:
                episodes.append(ep)
        
        # Sort episodes by season, then episode number
        episodes.sort(key=lambda e: (e['season'], e['episode']))
        
        # Remove page.on handler
        page.remove_listener('response', on_response)
        
        if INFO_MODE:
            print(f"INFO TV show '{page.evaluate('document.title')}' has {len(episodes)} episodes", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING _extract_tv_show_episodes failed: {e}", file=sys.stderr)
        # Try to return what we have
        try:
            page.remove_listener('response', on_response)
        except Exception:
            pass
    
    return episodes


# ============================================================
# Helper functions for interactive selection
# ============================================================


def read_with_esc(prompt: str) -> str:
    """Read user input. Returns 'ESC' if ESC key is pressed."""
    if HAS_KEYBOARD:
        # keyboard module can detect ESC
        print(prompt, end='', flush=True)
        # Wait up to 2 seconds for keyboard input
        import threading
        result = ['']
        
        def read_input():
            try:
                result[0] = input()
            except:
                pass
        
        t = threading.Thread(target=read_input, daemon=True)
        t.start()
        t.join(timeout=2)
        
        if not result[0]:
            # Check for ESC key
            if keyboard.is_pressed('esc'):
                return 'ESC'
            return ''
        return result[0].strip()
    else:
        # Fallback: use input() without ESC detection
        print(prompt, end='', flush=True)
        try:
            return input().strip()
        except EOFError:
            return ''


CONFIRM_KEYWORDS = {'y', 'yes', '确认', '是', '好', '下载'}



def _confirm_download(movies: list, category: str, section: str) -> bool:
    """Show movie list and confirm download.
    
    Returns True if user confirms (y), False if cancels (n).
    """
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"完整电影列表 (共 {len(movies)} 部):", file=sys.stderr)
    for i, movie in enumerate(movies):
        print(f"  {i+1}. {movie['title']}", file=sys.stderr)
    
    print(f"\n{'='*60}", file=sys.stderr)
    print("请确认下载:", file=sys.stderr)
    print("  - y: 确认开始下载", file=sys.stderr)
    print("  - n: 取消返回上级", file=sys.stderr)
    
    while True:
        answer = read_with_esc("\n请选择 (y/n): ")
        
        if answer == 'ESC':
            print("\nWARNING ESC 检测到 - 请重新输入", file=sys.stderr)
            continue
        
        if not answer:
            continue
        
        if answer.lower().strip() == 'y':
            return True
        elif answer.lower().strip() == 'n':
            return False
        
        print("WARNING 无效输入，请输入 y 或 n", file=sys.stderr)


def parse_selection_range(items: list, selection: str) -> list:
    """Parse user selection string into a list of matched items.
    
    Supports:
        - Single number: '1'
        - Range: '7-8' (inclusive)
        - Comma-separated: '1,4,6,7,10'
        - Mixed: '1,3-5,8'
    
    Args:
        items: List of items to select from
        selection: User's selection string
    
    Returns:
        List of matched items
    """
    if not items:
        return []
    
    selected = []
    seen_indices = set()
    
    for part in selection.split(','):
        part = part.strip()
        if not part:
            continue
        
        if '-' in part:
            # Range: '7-8'
            parts = part.split('-', 1)
            try:
                start = int(parts[0])
                end = int(parts[1])
                for i in range(start, end + 1):
                    idx = i - 1  # Convert 1-indexed to 0-indexed
                    if 0 <= idx < len(items) and idx not in seen_indices:
                        selected.append(items[idx])
                        seen_indices.add(idx)
            except ValueError:
                pass
        else:
            # Single number: '1'
            try:
                idx = int(part) - 1  # Convert 1-indexed to 0-indexed
                if 0 <= idx < len(items) and idx not in seen_indices:
                    selected.append(items[idx])
                    seen_indices.add(idx)
            except ValueError:
                pass
    
    return selected


# ============================================================
# Category & Section Priority Helpers
# ============================================================

_SPECIAL_CATEGORIES = ['Best of India', 'Made in South East Asia']


def category_rank(cat_name: str) -> int:
    """Return priority rank for a category. Lower = higher priority."""
    if cat_name == 'Best of India':
        return 0
    elif cat_name == 'Made in South East Asia':
        return 1
    return 2


def section_rank(sec_name: str) -> int:
    """Return priority rank for a section. Lower = higher priority."""
    name_lower = sec_name.lower()
    if 'top' in name_lower or 'popular' in name_lower:
        return 0
    elif 'latest' in name_lower:
        return 2
    return 1


def compare_priority(cat_a: str, sec_a: str, cat_b: str, sec_b: str) -> int:
    """Compare two (category, section) pairs.
    
    Returns >0 if a has higher priority, <0 if b has higher priority, 0 if equal.
    """
    rank_a = category_rank(cat_a)
    rank_b = category_rank(cat_b)
    if rank_a != rank_b:
        return rank_b - rank_a
    return section_rank(sec_b) - section_rank(sec_a)


def parse_refer_filename(middle_str: str) -> dict:
    """Parse category and section from refer_to_{middle}.txt filename.
    
    Strategy: match known special categories first, remainder is section.
    """
    middle_decoded = middle_str.replace('_', ' ')
    for cat in _SPECIAL_CATEGORIES:
        if middle_decoded.startswith(cat):
            remainder = middle_decoded[len(cat):].lstrip()
            return {'category': cat, 'section': remainder}
    # Not a special category → first word is category, rest is section
    parts = middle_decoded.split(' ', 1)
    return {'category': parts[0], 'section': parts[1] if len(parts) > 1 else ''}


def resolve_duplicate_folders(movies: list) -> None:
    """Check existing movie folders for duplicates and add/fix .refer_to markers.
    
    Only checks folders of movies that already have '_refer_to' in their dict.
    Uses filename scanning (not file content) to detect existing markers.
    
    Args:
        movies: List of movie dicts (mutated in-place to update category/section)
    """
    import glob
    base = os.path.join('data', 'subtitles')
    
    for movie in movies:
        if '_refer_to' not in movie:
            continue
        
        cat = movie.get('_category', 'unknown')
        sec = movie.get('_section', 'unknown')
        movie_title = movie.get('title', '')
        safe_movie = movie_title.replace('/', '_').replace('\\', '_').replace(':', '.')
        
        folder_path = os.path.join(base, cat, sec, safe_movie)
        if not os.path.isdir(folder_path):
            continue
        
        # Scan for refer_to_*.txt files (no need to read content)
        refer_files = glob.glob(os.path.join(folder_path, 'refer_to_*.txt'))
        current_refer = movie['_refer_to']  # {'category': ..., 'section': ...}
        
        if refer_files:
            # Folder already has a refer marker → parse and compare priority
            filename = os.path.basename(refer_files[0])
            middle = filename[len('refer_to_'):-len('.txt')]
            folder_refer = parse_refer_filename(middle)
            
            if compare_priority(
                folder_refer['category'], folder_refer['section'],
                current_refer['category'], current_refer['section']
            ) > 0:
                # Folder's refer has higher priority → update cached movie dict
                movie['_category'] = folder_refer['category']
                movie['_section'] = folder_refer['section']
                movie['_refer_to'] = folder_refer['category']
        else:
            # Folder exists but no refer marker → check if one is needed
            current_cat_rank = category_rank(current_refer['category'])
            current_sec_rank = section_rank(current_refer['section'])
            
            # Need a refer marker if current is NOT the highest priority
            # (i.e., there exists a higher-priority category/section for this movie)
            if current_cat_rank >= 2 or (current_cat_rank == 1):
                # Create the refer marker file
                ref_cat = current_refer['category'].replace(' ', '_')
                ref_sec = current_refer['section'].replace(' ', '_')
                refer_filename = f'refer_to_{ref_cat}_{ref_sec}.txt'
                refer_filepath = os.path.join(folder_path, refer_filename)
                open(refer_filepath, 'w').close()
                # Delete all .srt files in this folder (already in refer folder)
                for srt in glob.glob(os.path.join(folder_path, '*.srt')):
                    os.remove(srt)


def normalize_movie_id(url: str) -> str:
    """Extract the unique movie ID from a Prime Video URL.

    e.g., 'https://www.primevideo.com/detail/0TRR1D6Q5DYLIKHVXNBM0EV0PY/ref=atv_...'
    → '0TRR1D6Q5DYLIKHVXNBM0EV0PY'

    Args:
        url: Prime Video movie URL (may be relative or full, with or without ref params)

    Returns:
        The movie ID string, or the original URL if no ID found
    """
    import re
    match = re.search(r'/detail/([A-Z0-9]+)/', url)
    return match.group(1) if match else url


def collect_movies_from_items(page, items: list, category_name: str, cookies: list) -> list:
    """Collect movies from a list of items (categories or sections).
    
    For categories: extracts sections first (sorted by priority), then fetches movies.
    For sections: directly fetches movies from each section.
    Deduplicates movies by extracting the movie ID from URLs.
    
    Args:
        page: Playwright page object (shared browser context)
        items: List of items, each with 'href' and 'title' or 'name' keys
        category_name: Default category name for metadata (used for sections)
        cookies: Playwright cookies list
    
    Returns:
        List of movie dicts with '_category', '_section', and optionally '_refer_to' metadata
    """
    all_movies = []
    seen_ids = set()
    
    def add_movie(movie, category, section):
        """Add a movie to the list, deduplicating by movie ID."""
        movie_id = normalize_movie_id(movie['url'])
        if movie_id in seen_ids:
            # Duplicate: mark with reference to the original
            movie['_refer_to'] = {'category': category, 'section': section}
        else:
            seen_ids.add(movie_id)
        all_movies.append(movie)
    
    def sort_categories_by_priority(items):
        """Sort category items: Best of India → Made in South East Asia → others."""
        def cat_priority(item):
            name = item.get('title', item.get('name', ''))
            return category_rank(name)
        return sorted(items, key=lambda it: (cat_priority(it), it.get('title', '')))
    
    def sort_sections_by_priority(sections):
        """Sort sections: top/popular first, latest last, others in between."""
        def section_priority(sec_name):
            name_lower = sec_name.lower()
            if 'top' in name_lower or 'popular' in name_lower:
                return 0  # Highest priority
            elif 'latest' in name_lower:
                return 2  # Lowest priority
            return 1  # Normal
        
        return sorted(sections, key=lambda s: section_priority(s.get('title', '')))
    
    # Sort categories by priority (Best of India → Made in South East Asia → others)
    sorted_items = sort_categories_by_priority(items)
    
    for item in sorted_items:
        item_name = item.get('title', item.get('name', ''))
        item_href = item.get('href', '')
        if not item_href:
            continue
        
        # Use item's own name if it's a category, otherwise use category_name
        if 'name' in item:
            effective_category = item['name']
        else:
            effective_category = category_name
        
        # Check if this item is a category (needs section extraction) or a section
        if '/genre/' in item_href or '/collection/' in item_href:
            # Category: extract sections, sort by priority, then fetch movies
            sections = extract_sections_from_category(page, item_href, cookies)
            sorted_sections = sort_sections_by_priority(sections)
            for sec in sorted_sections:
                if sec.get('href'):
                    movies = fetch_section_movies(page, sec['href'], cookies)
                    for m in movies:
                        m['_category'] = effective_category
                        m['_section'] = sec['title']
                        add_movie(m, effective_category, sec['title'])
        else:
            # Section: fetch movies directly
            movies = fetch_section_movies(page, item_href, cookies)
            for m in movies:
                m['_category'] = effective_category
                m['_section'] = item_name
                add_movie(m, effective_category, item_name)
    
    return all_movies


def _retry_movies(page, failed_list: list, round_label: str) -> tuple:
    """Retry failed movie downloads.
    
    Args:
        page: Playwright page object
        failed_list: List of failed movie dicts with 'url', 'title', 'category', 'section'
        round_label: Label for log messages (e.g., '第一轮', '最终')
    
    Returns:
        (success_results, remaining_failures) where:
        - success_results: List of result dicts for movies that succeeded on retry
        - remaining_failures: List of failed movie dicts that still failed after retries
    """
    remaining = []
    success_results = []
    for fm in failed_list:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"INFO {round_label}: {fm['title']} (attempt 1/3)", file=sys.stderr)
        
        for attempt in range(3):
            result = extract_movie_subtitles(
                page, fm['url'],
                movie_title=fm['title'],
                category=fm['category'],
                section=fm['section']
            )
            if result.get('subtitles_saved', 0) > 0:
                print(f"INFO 重试成功: {fm['title']} (attempt {attempt+1}/3)", file=sys.stderr)
                success_results.append({
                    'title': fm['title'],
                    'category': fm['category'],
                    'section': fm['section'],
                    'success': True,
                    'subtitles_saved': result.get('subtitles_saved', 0),
                    'total_subtitle_types': result.get('total_subtitle_types', 0),
                    'filtered_subtitle_types': result.get('filtered_subtitle_types', 0),
                    'success_langs': result.get('success_langs', []),
                    'failed_langs': result.get('failed_langs', []),
                })
                break
            else:
                remaining_attempts = 2 - attempt
                if remaining_attempts > 0:
                    print(f"INFO 重试失败，还有 {remaining_attempts} 次机会: {fm['title']}", file=sys.stderr)
        else:
            # All 3 attempts failed
            remaining.append({
                'url': fm['url'],
                'title': fm['title'],
                'category': fm['category'],
                'section': fm['section'],
                'error': result.get('error', 'unknown'),
            })
            print(f"INFO 重试3次全部失败: {fm['title']}", file=sys.stderr)
    
    return success_results, remaining


def _build_download_result(result_dict: dict, movie_title: str, category: str, section: str) -> dict:
    """Build a standardized download result dict from extract_movie_subtitles output.
    
    Args:
        result_dict: Raw result from extract_movie_subtitles
        movie_title: Movie title
        category: Category name
        section: Section name
    
    Returns:
        Standardized result dict
    """
    return {
        'title': movie_title,
        'category': category,
        'section': section,
        'success': result_dict.get('subtitles_saved', 0) > 0,
        'subtitles_saved': result_dict.get('subtitles_saved', 0),
        'total_subtitle_types': result_dict.get('total_subtitle_types', 0),
        'filtered_subtitle_types': result_dict.get('filtered_subtitle_types', 0),
        'success_langs': result_dict.get('success_langs', []),
        'failed_langs': result_dict.get('failed_langs', []),
        'ignored_subtitles': result_dict.get('ignored_subtitles', 0),
        'ignored_reason': result_dict.get('ignored_reason', ''),
    }


def _get_user_input(prompt: str) -> tuple:
    """Get user input with ESC detection.
    
    Args:
        prompt: Input prompt string
    
    Returns:
        (selection, should_exit) where:
        - selection: User input string, or 'ESC' if escape pressed
        - should_exit: True if user pressed ESC at exit level
    """
    selection = read_with_esc(prompt)
    if selection == 'ESC':
        return 'ESC', True
    if not selection:
        return '', False
    return selection, False


def main():
    """Main function with hierarchical selection and caching.
    
    Uses a single shared Playwright browser/context/page instance
    across login, category extraction, and subtitle downloads.
    """
    email = "xing.c@hotmail.com"
    password = "789qweasd"
    
    # Single browser lifecycle management
    browser = None
    context = None
    page = None
    
    try:
        print("INFO Launching browser...", file=sys.stderr)
        os.makedirs('data/browser', exist_ok=True)
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False)
        state_file = 'data/browser/state.json'
        storage_state = None
        if os.path.exists(state_file):
            storage_state = state_file
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        
        # Login (skip if already logged in)
        is_logged_in, has_join_prime = _check_login_status(page)
        if is_logged_in:
            print("INFO 已登录，跳过登录步骤", file=sys.stderr)
            cookies = page.context.cookies()
        elif has_join_prime:
            # Page has visible Join Prime button - login directly
            print("INFO 检测到未登录，执行登录...", file=sys.stderr)
            login_result = login_prime_video(page, email, password)
            if not login_result['success']:
                print("ERROR Login failed", file=sys.stderr)
                sys.exit(1)
            cookies = login_result['cookies']
        else:
            # Navigation failed or uncertain - try login
            print("INFO 页面加载异常，尝试登录...", file=sys.stderr)
            login_result = login_prime_video(page, email, password)
            if not login_result['success']:
                print("ERROR Login failed", file=sys.stderr)
                sys.exit(1)
            cookies = login_result['cookies']
        
        # Save storage state for next session
        context.storage_state(path=state_file)
        
        # Extract categories only (FAST - no navigation to category pages)
        print("\nINFO Extracting categories from homepage...", file=sys.stderr)
        categories = extract_categories_only(page, cookies)
        
        if not categories:
            print("ERROR No categories found", file=sys.stderr)
            sys.exit(1)
        
        # State machine variables
        cache = {
            'sections': {},  # key: cat_idx -> [{'name': ..., 'href': ...}, ...]
            'movies': {}     # key: (cat_idx, sec_idx) -> [{'title': ..., 'url': ...}, ...]
        }
        
        # State: 'root' | 'sections' | 'movies'
        state = 'root'
        current_cat_idx = None  # Selected category index
        current_sec_idx = None  # Selected section index
        
        def go_to_root():
            """Reset state to root (category selector)."""
            nonlocal state, current_cat_idx, current_sec_idx
            state = 'root'
            current_cat_idx = None
            current_sec_idx = None
        
        def get_cat_name(idx):
            return categories[idx]['name'] if 0 <= idx < len(categories) else 'Unknown'
        
        while True:
            # ============================================================
            # STATE: root - Category selector
            # ============================================================
            if state == 'root':
                print(f"\n{'='*60}", file=sys.stderr)
                print("Prime Video 字幕下载器", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)
                print("可用类目:", file=sys.stderr)
                for i, cat in enumerate(categories):
                    print(f"  {i+1}. {cat['name']}", file=sys.stderr)
                print(f"\n选择方式:", file=sys.stderr)
                print("  - a/all: 下载所有类目下的所有电影", file=sys.stderr)
                print("  - 数字 (如 1, 1-3, 1,3,5): 进入该类目 / 选择多个类目", file=sys.stderr)
                print("  - b/back: 退出", file=sys.stderr)
                
                selection, should_exit = _get_user_input("\n请输入选择: ")
                if should_exit:
                    print("INFO 退出程序", file=sys.stderr)
                    break
                if not selection:
                    continue
                
                sel_lower = selection.lower().strip()
                
                if sel_lower in ('b', 'back'):
                    print("INFO 退出程序", file=sys.stderr)
                    break
                
                if sel_lower in ('a', 'all'):
                    # Download ALL categories
                    print("\nINFO 获取全部电影列表...", file=sys.stderr)
                    all_movies = collect_movies_from_items(page, categories, "all", cookies)
                    resolve_duplicate_folders(all_movies)
                    
                    if not all_movies:
                        print("WARNING 没有找到电影", file=sys.stderr)
                        continue
                    
                    if not _confirm_download(all_movies, "all", "all"):
                        print("INFO 已取消下载", file=sys.stderr)
                        continue
                    
                    download_movies(all_movies, page, "all", category="all", section="all")
                    go_to_root()
                    continue
                
                # Try multi-selection (supports single, range, comma-separated)
                selected_cats = parse_selection_range(categories, selection)
                
                if not selected_cats:
                    print(f"WARNING 未选择任何类目: {selection}", file=sys.stderr)
                    continue
                
                if len(selected_cats) == 1:
                    # Single category → enter sections state
                    cat = selected_cats[0]
                    cat_idx = categories.index(cat)
                    current_cat_idx = cat_idx
                    cat_name = cat['name']
                    cat_href = cat['href']
                    
                    print(f"\nINFO 进入类目: {cat_name}", file=sys.stderr)
                    
                    # Extract sections for this category
                    if cat_idx not in cache['sections']:
                        sections = extract_sections_from_category(page, cat_href, cookies)
                        cache['sections'][cat_idx] = sections
                    else:
                        sections = cache['sections'][cat_idx]
                    
                    if not sections:
                        print("WARNING 没有找到 sections", file=sys.stderr)
                        continue
                    
                    state = 'sections'
                else:
                    # Multiple categories → fetch all movies and download
                    print(f"\nINFO 选择 {len(selected_cats)} 个类目: {[c['name'] for c in selected_cats]}", file=sys.stderr)
                    all_movies = collect_movies_from_items(page, selected_cats, "", cookies)
                    resolve_duplicate_folders(all_movies)
                    
                    if not all_movies:
                        print("WARNING 没有找到电影", file=sys.stderr)
                        continue
                    
                    cat_names = ', '.join(c['name'] for c in selected_cats)
                    if not _confirm_download(all_movies, cat_names, "multiple categories"):
                        print("INFO 已取消下载", file=sys.stderr)
                        continue
                    
                    download_movies(all_movies, page, "multi-cat", category=cat_names, section="")
                    go_to_root()
            
            # ============================================================
            # STATE: sections - Section selector within a category
            # ============================================================
            elif state == 'sections':
                if current_cat_idx is None:
                    print("ERROR 状态错误", file=sys.stderr)
                    go_to_root()
                    continue
                
                sections = cache['sections'].get(current_cat_idx, [])
                cat_name = get_cat_name(current_cat_idx)
                
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"类目: {cat_name}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)
                print("Sections:", file=sys.stderr)
                for i, sec in enumerate(sections):
                    print(f"  {i+1}. {sec['title']} [NO URL]" if not sec.get('href') else f"  {i+1}. {sec['title']}", file=sys.stderr)
                
                print(f"\n选择方式:", file=sys.stderr)
                print("  - a/all: 下载此类目下所有 sections 的所有电影", file=sys.stderr)
                print("  - s/sec/section/sections: 查看 sections 列表", file=sys.stderr)
                print("  - 数字 (如 1, 1-3, 1,3,5): 进入该 section / 选择多个 section", file=sys.stderr)
                print("  - b/back: 返回类目选择", file=sys.stderr)
                
                selection, should_exit = _get_user_input("\n请输入选择: ")
                if should_exit:
                    print("INFO 退出程序", file=sys.stderr)
                    break
                if not selection:
                    continue
                
                sel_lower = selection.lower().strip()
                
                if sel_lower in ('b', 'back'):
                    go_to_root()
                    continue
                
                if sel_lower in ('a', 'all'):
                    # Download all sections in this category
                    print("\nINFO 获取此类目下所有电影...", file=sys.stderr)
                    all_movies = collect_movies_from_items(page, sections, cat_name, cookies)
                    resolve_duplicate_folders(all_movies)
                    
                    if not all_movies:
                        print("WARNING 没有找到电影", file=sys.stderr)
                        continue
                    
                    if not _confirm_download(all_movies, cat_name, ""):
                        print("INFO 已取消下载", file=sys.stderr)
                        continue
                    
                    download_movies(all_movies, page, "category", category=cat_name, section="")
                    go_to_root()
                    continue
                
                if sel_lower in ('s', 'sec', 'section', 'sections'):
                    # Show sections (already shown above, just re-prompt)
                    continue
                
                # Try multi-selection (supports single, range, comma-separated)
                selected_secs = parse_selection_range(sections, selection)
                
                if not selected_secs:
                    print(f"WARNING 未选择任何 section: {selection}", file=sys.stderr)
                    continue
                
                if len(selected_secs) == 1:
                    # Single section → enter movies state
                    sec = selected_secs[0]
                    sec_idx = sections.index(sec)
                    current_sec_idx = sec_idx
                    sec_name = sec['title']
                    sec_href = sec.get('href')
                    
                    if not sec_href:
                        print(f"WARNING Section '{sec_name}' 没有 URL，无法进入", file=sys.stderr)
                        continue
                    
                    # Fetch movies for this section (with caching)
                    cache_key = (current_cat_idx, sec_idx)
                    if cache_key not in cache['movies']:
                        print(f"\nINFO 导航到 Section 页面: {sec_href[:80]}...", file=sys.stderr)
                        movies = fetch_section_movies(page, sec_href, cookies)
                        for m in movies:
                            m['_category'] = cat_name
                            m['_section'] = sec_name
                        cache['movies'][cache_key] = movies
                    else:
                        movies = cache['movies'][cache_key]
                    
                    if not movies:
                        print("WARNING 没有找到电影", file=sys.stderr)
                        continue
                    
                    # Transition to movies state
                    state = 'movies'
                else:
                    # Multiple sections → fetch all movies and download
                    print(f"\nINFO 选择 {len(selected_secs)} 个 section: {[s['title'] for s in selected_secs]}", file=sys.stderr)
                    all_movies = collect_movies_from_items(page, selected_secs, cat_name, cookies)
                    resolve_duplicate_folders(all_movies)
                    
                    if not all_movies:
                        print("WARNING 没有找到电影", file=sys.stderr)
                        continue
                    
                    sec_names = ', '.join(s['title'] for s in selected_secs)
                    if not _confirm_download(all_movies, cat_name, sec_names):
                        print("INFO 已取消下载", file=sys.stderr)
                        continue
                    
                    download_movies(all_movies, page, "multi-sec", category=cat_name, section=sec_names)
                    go_to_root()
            
            # ============================================================
            # STATE: movies - Movie selector within a section
            # ============================================================
            elif state == 'movies':
                if current_cat_idx is None or current_sec_idx is None:
                    print("ERROR 状态错误", file=sys.stderr)
                    go_to_root()
                    continue
                
                cache_key = (current_cat_idx, current_sec_idx)
                movies = cache['movies'].get(cache_key, [])
                cat_name = get_cat_name(current_cat_idx)
                sec_name = sections[current_sec_idx]['title'] if current_sec_idx < len(sections) else 'Unknown'
                
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"Section: {sec_name}", file=sys.stderr)
                print(f"{'='*60}", file=sys.stderr)
                print(f"电影列表 (共 {len(movies)} 部):", file=sys.stderr)
                for i, movie in enumerate(movies):
                    print(f"  {i+1}. {movie['title']}", file=sys.stderr)
                
                print(f"\n选择方式:", file=sys.stderr)
                print("  - a/all: 下载此 section 下所有电影", file=sys.stderr)
                print("  - m/movie/movies: 选择具体电影", file=sys.stderr)
                print("  - 数字 (如 1, 1-5, 1,3,5): 下载该电影 / 选择多个电影", file=sys.stderr)
                print("  - b/back: 返回 section 选择", file=sys.stderr)
                
                selection, should_exit = _get_user_input("\n请输入选择: ")
                if should_exit:
                    print("INFO 退出程序", file=sys.stderr)
                    break
                if not selection:
                    continue
                
                sel_lower = selection.lower().strip()
                
                if sel_lower in ('b', 'back'):
                    # Go back to sections state (not root), preserving current_cat_idx
                    state = 'sections'
                    continue
                
                if sel_lower in ('a', 'all'):
                    # Download all movies in this section
                    if not _confirm_download(movies, cat_name, sec_name):
                        print("INFO 已取消下载", file=sys.stderr)
                        continue
                    
                    download_movies(movies, page, "section", category=cat_name, section=sec_name)
                    go_to_root()
                    continue
                
                if sel_lower in ('m', 'movie', 'movies'):
                    # Select specific movies
                    print(f"\n{'='*60}", file=sys.stderr)
                    print("请选择电影 (编号, 如 1, 1-5, 1,3,5, all):", file=sys.stderr)
                    print("  - b/back: 返回上一级", file=sys.stderr)
                    
                    while True:
                        movie_selection = read_with_esc("\n请输入选择: ")
                        if movie_selection == 'ESC':
                            print("INFO 退出程序", file=sys.stderr)
                            go_to_root()
                            break
                        if not movie_selection:
                            continue
                        
                        ms_lower = movie_selection.lower().strip()
                        
                        if ms_lower in ('b', 'back'):
                            break
                        
                        if ms_lower in ('a', 'all'):
                            if not _confirm_download(movies, cat_name, sec_name):
                                print("INFO 已取消下载", file=sys.stderr)
                                break
                            download_movies(movies, page, "section", category=cat_name, section=sec_name)
                            go_to_root()
                            break
                        
                        # Parse movie indices using parse_selection_range
                        selected_movies = parse_selection_range(movies, movie_selection)
                        
                        if selected_movies:
                            if not _confirm_download(selected_movies, cat_name, sec_name):
                                print("INFO 已取消下载", file=sys.stderr)
                                break
                            download_movies(selected_movies, page, "movie", category=cat_name, section=sec_name)
                            go_to_root()
                            break
                        else:
                            print("WARNING 未选择任何电影", file=sys.stderr)
                    
                    if state == 'movies':  # Still in movies state (didn't exit)
                        continue
                    continue
                
                # Try multi-selection (supports single, range, comma-separated)
                selected_movies = parse_selection_range(movies, selection)
                
                if not selected_movies:
                    print(f"WARNING 未选择任何电影: {selection}", file=sys.stderr)
                    continue
                
                if not _confirm_download(selected_movies, cat_name, sec_name):
                    print("INFO 已取消下载", file=sys.stderr)
                    continue
                
                download_movies(selected_movies, page, "movie", category=cat_name, section=sec_name)
                go_to_root()
            
            else:
                print(f"WARNING 未知状态: {state}", file=sys.stderr)
                go_to_root()
    
    finally:
        # Cleanup browser resources
        if context:
            try:
                context.close()
            except Exception:
                pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        try:
            p.stop()
        except Exception:
            pass

def download_movies(movies: list, page, context: str = "", category: str = "", section: str = "", failed_movies: list = None) -> list:
    """Download subtitles for a list of movies and TV shows.
    
    Flow per item:
    1. Navigate to URL
    2. Detect movie/tv_show
    3. If movie: download subtitle
    4. If TV show: expand all episodes, then download subtitles for each episode
    
    Args:
        movies: List of item dicts (each has 'title', 'url', and optionally 'type')
        page: Playwright page object (shared browser context)
        context: Context string for logging (category/section/movie)
        category: Category name for directory structure
        section: Section name for directory structure
        failed_movies: List to collect failed movie entries (for retry)
    
    Returns:
        List of download result dicts: [{'title', 'category', 'section', 'success', ...}, ...]
    """
    if not movies:
        print("WARNING 没有电影可下载", file=sys.stderr)
        return []
    
    if failed_movies is None:
        failed_movies = []
    
    results = []
    item_index = 0
    tv_show_count = 0
    movie_count = 0
    
    for movie in movies:
        movie_title = movie.get('title', '')
        movie_url = movie.get('url', '')
        movie_section = movie.get('_section', section)
        
        # Skip referenced items (already downloaded in another section)
        if '_refer_to' in movie:
            ref = movie['_refer_to']
            print(f"INFO 跳过重复: {movie_title} (refer to {ref['category']} -> {ref['section']})", file=sys.stderr)
            results.append({
                'title': movie_title,
                'category': category,
                'section': movie_section,
                'success': True,
                'subtitles_saved': 0,
                'total_subtitle_types': 0,
                'filtered_subtitle_types': 0,
                'success_langs': [],
                'failed_langs': [],
                'ignored_subtitles': 0,
                'ignored_reason': f"referenced to {ref['category']} -> {ref['section']}",
            })
            continue
        
        # Step 1: Navigate to URL
        try:
            page.goto(movie_url if movie_url.startswith('http') else 'https://www.primevideo.com' + movie_url, timeout=20000)
            page.wait_for_load_state('domcontentloaded')
            time.sleep(1)
        except Exception as e:
            print(f"WARNING Failed to navigate to {movie_title}: {e}", file=sys.stderr)
            results.append({
                'title': movie_title,
                'category': category,
                'section': movie_section,
                'success': False,
                'subtitles_saved': 0,
                'total_subtitle_types': 0,
                'filtered_subtitle_types': 0,
                'success_langs': [],
                'failed_langs': [],
                'ignored_subtitles': 0,
                'ignored_reason': f"navigation failed: {e}",
            })
            continue
        
        # Step 2: Detect movie/tv_show
        is_tv_show = False
        try:
            # Check for season selector
            has_season_selector = page.evaluate('''() => {
                const links = document.querySelectorAll('a._1NNx6V');
                for (const link of links) {
                    const text = link.textContent?.trim();
                    if (text && text.match(/Season\\s*\\d+/i)) {
                        return true;
                    }
                }
                return false;
            }''')
            
            if not has_season_selector:
                # Method 2: Check page JSON for episodes
                has_episodes = page.evaluate('''() => {
                    let props = undefined;
                    for (const script of document.querySelectorAll('script[type="application/json"]')) {
                        try {
                            const data = JSON.parse(script.innerHTML);
                            if (data && data.init && data.init.preparations && data.init.preparations.body) {
                                const body = data.init.preparations.body;
                                if (body.atf && body.btf) {
                                    props = body;
                                    break;
                                }
                            }
                        } catch(e) {}
                    }
                    if (!props) return false;
                    
                    const detail = props.btf.state.detail;
                    for (const sectionKey of Object.keys(detail)) {
                        const section = detail[sectionKey];
                        if (typeof section !== 'object' || section === null) continue;
                        for (const [id, d] of Object.entries(section)) {
                            if (d && d.titleType === 'episode') {
                                return true;
                            }
                        }
                    }
                    return false;
                }''')
                
                if has_episodes:
                    has_season_selector = True
            
            is_tv_show = has_season_selector
        except Exception as e:
            if DEBUG_MODE:
                print(f"DEBUG Title type detection failed for {movie_title}: {e}", file=sys.stderr)
        
        # Step 3 & 4: Handle based on type
        if is_tv_show:
            # TV show: expand all episodes, then download subtitles for each
            tv_show_count += 1
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"INFO 检测到剧集: {movie_title}", file=sys.stderr)
            
            try:
                episodes = _extract_tv_show_episodes(page, movie_url)
                if not episodes:
                    print(f"WARNING 未找到剧集 {movie_title} 的集数，作为电影处理", file=sys.stderr)
                    is_tv_show = False
            except Exception as e:
                if DEBUG_MODE:
                    print(f"DEBUG TV show episode extraction failed for {movie_title}: {e}", file=sys.stderr)
                print(f"WARNING 剧集 {movie_title} 集数提取失败，作为电影处理", file=sys.stderr)
                is_tv_show = False
        
        if is_tv_show:
            # TV show: download subtitles for all episodes
            series_name = movie_title
            safe_series = series_name.replace('/', '_').replace('\\', '_').replace(':', '.')
            safe_cat = category.replace('/', '_').replace('\\', '_').replace(':', '.') if category else 'unknown'
            output_dir = os.path.join('data', 'subtitles', safe_cat, safe_series)
            os.makedirs(output_dir, exist_ok=True)
            
            for ep in episodes:
                item_index += 1
                ep_season = ep.get('season', 0)
                ep_number = ep.get('episode', 0)
                ep_title = ep.get('title', '')
                ep_url = ep.get('url', '')
                
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"INFO 处理 {item_index}/{len(movies)}: {series_name} S{ep_season:02d}E{ep_number:02d}: {ep_title}", file=sys.stderr)
                
                # Build filename: SeriesName.S{season}E{episode}.lang[cc].srt
                ep_filename = f"S{ep_season:02d}E{ep_number:02d}"
                
                result = extract_movie_subtitles(
                    page, ep_url,
                    movie_title=f"{series_name}.S{ep_season:02d}E{ep_number:02d}",
                    category=category,
                    section=movie_section,
                    _tv_show_dir=output_dir,
                    _tv_show_filename=ep_filename,
                )
                
                if DEBUG_MODE:
                    print(f"INFO 剧集结果: {json.dumps(result, indent=2, ensure_ascii=False)}", file=sys.stderr)
                
                ep_result = _build_download_result(
                    result, f"{series_name} S{ep_season:02d}E{ep_number:02d}",
                    category, movie_section
                )
                results.append(ep_result)
                
                # Collect failed episodes for retry
                if not result.get('subtitles_saved', 0) > 0:
                    failed_movies.append({
                        'url': ep_url,
                        'title': f"{series_name} S{ep_season:02d}E{ep_number:02d}",
                        'category': category,
                        'section': movie_section,
                        'error': result.get('error', 'unknown'),
                    })
        else:
            # Movie: download subtitle
            movie_count += 1
            item_index += 1
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"INFO 处理 {item_index}/{len(movies)}: {movie_title}", file=sys.stderr)
            
            result = extract_movie_subtitles(
                page, movie_url,
                movie_title=movie_title,
                category=category,
                section=movie_section
            )
            if DEBUG_MODE:
                print(f"INFO 电影结果: {json.dumps(result, indent=2, ensure_ascii=False)}", file=sys.stderr)
            results.append(_build_download_result(result, movie_title, category, movie_section))
            
            # Collect failed movies for retry
            if not result.get('subtitles_saved', 0) > 0:
                failed_movies.append({
                    'url': movie_url,
                    'title': movie_title,
                    'category': category,
                    'section': movie_section,
                    'error': result.get('error', 'unknown'),
                })
    
    # Retry failed movies: 3 attempts each
    if failed_movies:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"INFO 第一轮有 {len(failed_movies)} 个电影失败，开始重试（最多3次）...", file=sys.stderr)
        
        retry_results, retry_remaining = _retry_movies(page, failed_movies, "第一轮")
        results.extend(retry_results)
        
        # Final retry round: 3 more attempts for remaining failures
        if retry_remaining:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"INFO 最终重试: {len(retry_remaining)} 个电影仍失败，再试3次...", file=sys.stderr)
            
            final_results, final_remaining = _retry_movies(page, retry_remaining, "最终")
            results.extend(final_results)
            
            # Report final failures
            if final_remaining:
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"INFO 最终仍有 {len(final_remaining)} 个电影失败:", file=sys.stderr)
                for fm in final_remaining:
                    print(f"  - {fm['title']}: {fm['error']}", file=sys.stderr)
            else:
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"INFO 所有失败电影最终重试成功!", file=sys.stderr)
    
    success_count = sum(1 for r in results if r['success'])
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"INFO 下载完成: {success_count}/{len(movies)} 个电影成功", file=sys.stderr)
    
    # Print old summary
    if results:
        _print_download_summary(results)
    
    return results


def _print_download_summary(results: list) -> None:
    """Print a formatted summary of downloaded subtitles.
    
    Groups by category -> section, showing successful downloads and ignored movies.
    """
    # Group by category -> section
    grouped = {}
    for r in results:
        if not r['success']:
            continue
        cat = r.get('category', 'Unknown')
        sec = r.get('section', 'Unknown')
        if cat not in grouped:
            grouped[cat] = {}
        if sec not in grouped[cat]:
            grouped[cat][sec] = []
        grouped[cat][sec].append(r)
    
    # Collect ignored movies
    ignored_movies = []
    for r in results:
        if not r['success']:
            continue
        ignored = r.get('ignored_subtitles', 0)
        reason = r.get('ignored_reason', '')
        if ignored > 0 or reason:
            ignored_movies.append({
                'title': r['title'],
                'category': r['category'],
                'section': r['section'],
                'ignored': ignored,
                'reason': reason,
            })
    
    if not grouped and not ignored_movies:
        print("\nINFO 没有成功下载任何字幕", file=sys.stderr)
        return
    
    total = sum(len(movies) for cats in grouped.values() for movies in cats.values())
    total_ignored = len(ignored_movies)
    
    print(f"\n{'='*60}", file=sys.stderr)
    print("下载完成总结", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"总电影数: {total}", file=sys.stderr)
    if total_ignored > 0:
        print(f"忽略: {total_ignored} 个（已存在/已引用）", file=sys.stderr)
    
    for cat in sorted(grouped.keys()):
        print(f"\n[{cat}]", file=sys.stderr)
        for sec in sorted(grouped[cat].keys()):
            movies = grouped[cat][sec]
            print(f"  [{sec}]", file=sys.stderr)
            for r in movies:
                title = r['title']
                ignored = r.get('ignored_subtitles', 0)
                reason = r.get('ignored_reason', '')
                if reason:
                    print(f"    - {title} (refer to {reason})", file=sys.stderr)
                elif ignored > 0:
                    print(f"    - {title} ✓ (忽略{ignored}个已存在字幕)", file=sys.stderr)
                else:
                    print(f"    - {title} ✓", file=sys.stderr)
    
    if ignored_movies:
        print(f"\n被忽略的电影:", file=sys.stderr)
        for im in ignored_movies:
            if im['reason']:
                print(f"  - {im['title']} (refer to {im['reason']})", file=sys.stderr)
            elif im['ignored'] > 0:
                print(f"  - {im['title']} (本地已有{im['ignored']}个字幕)", file=sys.stderr)
    
    print(f"\n{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
