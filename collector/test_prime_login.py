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
        print("INFO Navigating to Prime Video homepage...", file=sys.stderr)
        page.goto("https://www.primevideo.com", timeout=30000)
        time.sleep(5)
        
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
        time.sleep(8)
        
        print("INFO   Scrolling to load all sections...", file=sys.stderr)
        for _scroll in range(3):
            page.evaluate('window.scrollBy(0, window.innerHeight)')
            time.sleep(2)
        
        # Use the EXACT same JS as extract_category_tree (proven working)
        # Split into two evaluate calls to debug
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
                for (const link of container.querySelectorAll("a")) {
                    if (link.textContent.includes("See more") || link.textContent.includes("See More")) {
                        seeMoreHref = link.getAttribute("href");
                        break;
                    }
                }
                
                let sectionHref = seeMoreHref;
                if (!sectionHref) {
                    const par = container.parentElement;
                    if (par) {
                        for (const link of par.querySelectorAll("a")) {
                            const href = link.getAttribute("href");
                            if (href && href.includes("/browse/")) {
                                sectionHref = href.startsWith('http') ? href : 'https://www.primevideo.com' + href;
                                break;
                            }
                        }
                    }
                }
                
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
            has_url = sec.get('href') and sec['href'].startswith('http')
            print(f"    {i+1}. {sec.get('title', '?')} {'[URL] ' if has_url else '[NO URL]'}", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING extract_sections_from_category failed: {e}", file=sys.stderr)
        return []
    
    return sections_js


def extract_movie_subtitles(page, movie_url: str, movie_title: str = '', category: str = '', section: str = '') -> dict:
    """Extract subtitles from a Prime Video movie using playback envelope API.
    
    Args:
        page: Playwright page object (shared browser context)
        movie_url: Movie page URL
        movie_title: Movie title for display and filename
        category: Category name for directory structure
        section: Section name for directory structure
    
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
            
            filtered_subtitles.append({
                'lang_code': lang_code,
                'type': sub_type,
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
            srt_content = None
            
            # Retry mechanism: 3s wait, max 3 retries
            max_retries = 3
            for attempt in range(max_retries):
                srt_content = fetch_subtitle(sub['url'])
                if srt_content:
                    break
                if attempt < max_retries - 1:
                    print(f"WARNING Retry {attempt+1}/{max_retries-1} for {lang_code} subtitle...", file=sys.stderr)
                    time.sleep(3)
            
            if not srt_content:
                print(f"WARNING Failed to fetch subtitle after {max_retries} attempts: {lang_code} ({sub['type']})", file=sys.stderr)
                failed_langs.append(lang_code)
                continue
            
            filename = build_filename(safe_movie, lang_code, sub['type'])
            filepath = os.path.join(output_dir, f"{filename}.srt")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            caption_count = srt_content.count('\n\n')
            if DEBUG_MODE:
                print(f"INFO Saved: {filepath} ({caption_count} captions, type={sub['type']})", file=sys.stderr)
            saved_count += 1
            downloaded_langs.add(lang_code)
        
        # Update result with actual download status
        result['subtitles_saved'] = saved_count
        result['subtitle_dir'] = output_dir
        result['success_langs'] = sorted(downloaded_langs)
        result['failed_langs'] = failed_langs
        # Language codes are like 'ta-in', 'en-us', 'kn-in', etc.
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
        if error:
            print(f"{result.get('title', 'unknown')}: 失败 - {error}", file=sys.stderr)
        else:
            success_count_movie = len(downloaded_langs)
            failed_count_movie = len(failed_langs)
            success_str = f"成功{success_count_movie}个" if downloaded_langs else "成功0个"
            failed_str = f"失败{failed_count_movie}个({', '.join(sorted(failed_langs))})" if failed_langs else "失败0个"
            print(f"{result.get('title', 'unknown')}: {result['total_subtitle_types']}种字幕 → 筛选后{result['filtered_subtitle_types']}种 ({', '.join(sorted(downloaded_langs))}) → {success_str}, {failed_str}", file=sys.stderr)
    
    except Exception as e:
        print(f"ERROR extract_movie_subtitles failed: {e}", file=sys.stderr)
        result['error'] = str(e)
        result['total_subtitle_types'] = 0
        result['filtered_subtitle_types'] = 0
        result['success_langs'] = []
        result['failed_langs'] = []
        return result
    
    return result

def _extract_section_movies_from_category(page, category_url: str, section_title: str, cookies: list) -> list:
    """Navigate to category page, find target section, click 'See more' to go to section page,
    then use shared scroll-and-collect logic to get all movies.
    
    Uses shared page object.
    
    Args:
        page: Playwright page object (shared browser context)
        category_url: The category page URL
        section_title: The title of the target section to extract movies from
        cookies: Playwright cookies list
    
    Returns:
        List of all movie dicts from the target section
    """
    try:
        # Navigate to category page
        if category_url.startswith('http'):
            full_url = category_url
        else:
            full_url = 'https://www.primevideo.com' + category_url
        
        print(f"INFO   Navigating to: {full_url[:100]}...", file=sys.stderr)
        page.goto(full_url, timeout=30000)
        time.sleep(8)
        
        # Scroll to load all sections
        print(f"INFO   Scrolling to load all sections...", file=sys.stderr)
        for _scroll in range(2):
            page.evaluate('window.scrollBy(0, window.innerHeight)')
            time.sleep(2)
        
        # Find target section's "See more" link
        section_href = page.evaluate('''(sectionTitle) => {
            const allContainers = document.querySelectorAll("[class*='carousel'], [class*='cards'], [class*='card']");
            for (const container of allContainers) {
                let title = "";
                let parent = container.parentElement;
                while (parent && !title) {
                    const titleEl = parent.querySelector('h2.headerComponents-qwttco');
                    if (titleEl) { title = titleEl.textContent.trim(); break; }
                    parent = parent.parentElement;
                    if (parent && parent.tagName === 'BODY') break;
                }
                if (title === sectionTitle) {
                    // Find "See more" link
                    for (const link of container.querySelectorAll("a")) {
                        if (link.textContent.includes("See more") || link.textContent.includes("See More")) {
                            const href = link.getAttribute("href");
                            if (href) return href.startsWith('http') ? href : 'https://www.primevideo.com' + href;
                        }
                    }
                    // Fallback: find any /browse/ link in parent
                    const par = container.parentElement;
                    if (par) {
                        for (const link of par.querySelectorAll("a")) {
                            const href = link.getAttribute("href");
                            if (href && href.includes("/browse/")) {
                                return href.startsWith('http') ? href : 'https://www.primevideo.com' + href;
                            }
                        }
                    }
                }
            }
            return null;
        }''', section_title)
        
        if not section_href:
            print(f"WARNING Could not find 'See more' link for section '{section_title}'", file=sys.stderr)
            return []
        
        print(f"INFO   Found section URL: {section_href[:80]}...", file=sys.stderr)
        
        # Navigate to section page
        page.goto(section_href, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        
        # Reuse fetch_section_movies logic inline
        extract_js = '''() => {
            const movies = [];
            for (const link of document.querySelectorAll("a[href*='/detail/']")) {
                const href = link.getAttribute("href");
                if (!href) continue;
                const url = href.startsWith('http') ? href : 'https://www.primevideo.com' + href;
                const title = link.textContent?.trim() || "";
                if (title && title.length > 2 && title.length < 100) {
                    movies.push({ url, title });
                }
            }
            return movies;
        }'''
        
        seen_urls = {}
        consecutive_no_new = 0
        scroll_count = 0
        
        while scroll_count < 15:
            page.evaluate('window.scrollBy(0, 500)')
            time.sleep(1)
            
            current_movies = page.evaluate(extract_js)
            new_count = 0
            for m in current_movies:
                if m['url'] not in seen_urls:
                    seen_urls[m['url']] = m['title']
                    new_count += 1
            
            total = len(seen_urls)
            if new_count > 0:
                if INFO_MODE:
                    print(f"INFO Scroll #{scroll_count + 1}: {total} movies total, {new_count} new", file=sys.stderr)
                consecutive_no_new = 0
            else:
                consecutive_no_new += 1
                if INFO_MODE:
                    print(f"INFO Scroll #{scroll_count + 1}: {total} movies total, no new (streak: {consecutive_no_new})", file=sys.stderr)
            
            scroll_count += 1
            if consecutive_no_new >= 3:
                if INFO_MODE:
                    print(f"INFO Stable for 3 scrolls at {total} movies - stopping", file=sys.stderr)
                break
        
        all_movies = [{'title': title, 'url': url} for url, title in seen_urls.items()]
        print(f"INFO   Found {len(all_movies)} movies in section '{section_title}'", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING _extract_section_movies_from_category failed: {e}", file=sys.stderr)
        return []
    
    return all_movies


def fetch_section_movies(page, section_url: str, cookies: list) -> list:
    """Navigate to section page, scroll to collect all movies (virtual scrolling aware), and extract all movies.
    
    Uses shared page object. Prime Video uses virtual scrolling: movies outside viewport are removed from DOM.
    Strategy: scroll incrementally, extract {url, title} each time, accumulate by URL.
    Stop when 3 consecutive scrolls yield no new URLs.
    
    Args:
        page: Playwright page object (shared browser context)
        section_url: The 'See more' URL for the section
        cookies: Playwright cookies list
    
    Returns:
        List of movie dicts: [{'title': '...', 'url': '...'}, ...]
    """
    extract_js = '''() => {
        const movies = [];
        for (const link of document.querySelectorAll("a[href*='/detail/']")) {
            const href = link.getAttribute("href");
            if (!href) continue;
            const url = href.startsWith('http') ? href : 'https://www.primevideo.com' + href;
            const title = link.textContent?.trim() || "";
            if (title && title.length > 2 && title.length < 100) {
                movies.push({ url, title });
            }
        }
        return movies;
    }'''
    
    all_movies = []
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
        time.sleep(5)
        
        # Scroll and accumulate movies
        consecutive_no_new = 0
        scroll_count = 0
        
        while scroll_count < 15:
            page.evaluate('window.scrollBy(0, 500)')
            time.sleep(1)
            
            current_movies = page.evaluate(extract_js)
            new_count = 0
            for m in current_movies:
                if m['url'] not in seen_urls:
                    seen_urls[m['url']] = m['title']
                    new_count += 1
            
            total = len(seen_urls)
            if new_count > 0:
                if INFO_MODE:
                    print(f"INFO Scroll #{scroll_count + 1}: {total} movies total, {new_count} new", file=sys.stderr)
                consecutive_no_new = 0
            else:
                consecutive_no_new += 1
                if INFO_MODE:
                    print(f"INFO Scroll #{scroll_count + 1}: {total} movies total, no new (streak: {consecutive_no_new})", file=sys.stderr)
            
            scroll_count += 1
            if consecutive_no_new >= 3:
                if INFO_MODE:
                    print(f"INFO Stable for 3 scrolls at {total} movies - stopping", file=sys.stderr)
                break
        
        all_movies = [{'title': title, 'url': url} for url, title in seen_urls.items()]
        print(f"INFO Total movies collected: {len(all_movies)}", file=sys.stderr)
    
    except Exception as e:
        print(f"WARNING fetch_section_movies failed: {e}", file=sys.stderr)
        return []
    
    return all_movies


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


def build_tree_display(tree: list) -> str:
    """Build a tree display string for the given tree.
    
    Format:
    1. Best of India
       1.1. Movies in Tamil
         1.1.1 Bigil
         1.1.2 Coolie
         1.1.3 Varisu
       1.2. Movies in Telugu
    2. Other Category
       2.1. Section A
    """
    lines = []
    for cat_idx, category in enumerate(tree):
        cat_num = cat_idx + 1
        lines.append(f"{cat_num}. {category['name']}")
        
        for sec_idx, section in enumerate(category['sections']):
            sec_num = sec_idx + 1
            sec_name = section.get('title', section.get('name', 'Unknown'))
            lines.append(f"  {cat_num}.{sec_num}. {sec_name}")
            
            # Show numbered movies under each section
            movies = section.get('example_movies', [])
            for mov_idx, movie in enumerate(movies):
                mov_num = mov_idx + 1
                lines.append(f"    {cat_num}.{sec_num}.{mov_num}. {movie['title']}")
    
    return '\n'.join(lines)


def build_partial_tree_display(tree: list, match_info: dict) -> str:
    """Build a tree display showing only the matching path.
    
    match_info structure:
    {
        'type': 'category' | 'section' | 'movie',
        'cat_idx': int,
        'sec_idx': int or None,
        'mov_idx': int or None,
        'matched_items': [...]
    }
    """
    lines = []
    
    if match_info['type'] == 'category':
        cat = tree[match_info['cat_idx']]
        cat_num = match_info['cat_idx'] + 1
        lines.append(f"{cat_num}. {cat['name']}")
        for sec_idx, section in enumerate(cat['sections']):
            sec_num = sec_idx + 1
            sec_name = section.get('title', section.get('name', 'Unknown'))
            lines.append(f"  {cat_num}.{sec_num}. {sec_name}")
    
    elif match_info['type'] == 'section':
        cat = tree[match_info['cat_idx']]
        cat_num = match_info['cat_idx'] + 1
        sec = cat['sections'][match_info['sec_idx']]
        sec_num = match_info['sec_idx'] + 1
        sec_name = sec.get('title', sec.get('name', 'Unknown'))
        lines.append(f"{cat_num}. {cat['name']}")
        lines.append(f"  {cat_num}.{sec_num}. {sec_name}")
    
    elif match_info['type'] == 'movie':
        cat = tree[match_info['cat_idx']]
        cat_num = match_info['cat_idx'] + 1
        sec = cat['sections'][match_info['sec_idx']]
        sec_num = match_info['sec_idx'] + 1
        sec_name = sec.get('title', sec.get('name', 'Unknown'))
        mov = sec.get('example_movies', [])[match_info['mov_idx']]
        mov_num = match_info['mov_idx'] + 1
        lines.append(f"{cat_num}. {cat['name']}")
        lines.append(f"  {cat_num}.{sec_num}. {sec_name}")
        lines.append(f"    {cat_num}.{sec_num}.{mov_num}. {mov['title']}")
    
    return '\n'.join(lines)


def parse_selection(selection_str: str, tree: list) -> dict:
    """Parse a numeric selection string and return item indices.
    
    Returns:
    {
        'type': 'category' | 'section' | 'movie',
        'cat_idx': int,
        'sec_idx': int or None,
        'mov_idx': int or None,
        'movies': list of movie dicts
    }
    """
    parts = selection_str.strip().split('.')
    
    if len(parts) == 1:
        # Category level
        cat_idx = int(parts[0]) - 1
        if cat_idx < 0 or cat_idx >= len(tree):
            return {'error': f'Invalid category index: {parts[0]}'}
        
        # Collect all movies in this category
        movies = []
        for section in tree[cat_idx]['sections']:
            movies.extend(section.get('example_movies', []))
        
        return {
            'type': 'category',
            'cat_idx': cat_idx,
            'sec_idx': None,
            'mov_idx': None,
            'movies': movies
        }
    
    elif len(parts) == 2:
        # Section level
        cat_idx = int(parts[0]) - 1
        sec_idx = int(parts[1]) - 1
        if cat_idx < 0 or cat_idx >= len(tree):
            return {'error': f'Invalid category index: {parts[0]}'}
        if sec_idx < 0 or sec_idx >= len(tree[cat_idx]['sections']):
            return {'error': f'Invalid section index: {parts[1]}'}
        
        section = tree[cat_idx]['sections'][sec_idx]
        movies = section.get('example_movies', [])
        
        return {
            'type': 'section',
            'cat_idx': cat_idx,
            'sec_idx': sec_idx,
            'mov_idx': None,
            'movies': movies
        }
    
    elif len(parts) == 3:
        # Movie level
        cat_idx = int(parts[0]) - 1
        sec_idx = int(parts[1]) - 1
        mov_idx = int(parts[2]) - 1
        if cat_idx < 0 or cat_idx >= len(tree):
            return {'error': f'Invalid category index: {parts[0]}'}
        if sec_idx < 0 or sec_idx >= len(tree[cat_idx]['sections']):
            return {'error': f'Invalid section index: {parts[1]}'}
        section = tree[cat_idx]['sections'][sec_idx]
        example_movies = section.get('example_movies', [])
        if mov_idx < 0 or mov_idx >= len(example_movies):
            return {'error': f'Invalid movie index: {parts[2]}'}
        
        movie = example_movies[mov_idx]
        
        return {
            'type': 'movie',
            'cat_idx': cat_idx,
            'sec_idx': sec_idx,
            'mov_idx': mov_idx,
            'movies': [movie]
        }
    
    return {'error': f'Invalid selection format: {selection_str}'}


def find_items_by_name(tree: list, name: str) -> dict:
    """Find items by name (partial match, case-insensitive).
    
    Returns match_info dict or error dict.
    """
    name_lower = name.lower().strip()
    
    # Search for category
    for cat_idx, category in enumerate(tree):
        if name_lower in category['name'].lower():
            return {
                'type': 'category',
                'cat_idx': cat_idx,
                'sec_idx': None,
                'mov_idx': None,
                'matched': category['name']
            }
    
    # Search for section
    for cat_idx, category in enumerate(tree):
        for sec_idx, section in enumerate(category['sections']):
            sec_name = section.get('title', section.get('name', ''))
            if name_lower in sec_name.lower():
                return {
                    'type': 'section',
                    'cat_idx': cat_idx,
                    'sec_idx': sec_idx,
                    'mov_idx': None,
                    'matched': sec_name
                }
    
    # Search for movie
    for cat_idx, category in enumerate(tree):
        for sec_idx, section in enumerate(category['sections']):
            for mov_idx, movie in enumerate(section.get('example_movies', [])):
                if name_lower in movie['title'].lower():
                    return {
                        'type': 'movie',
                        'cat_idx': cat_idx,
                        'sec_idx': sec_idx,
                        'mov_idx': mov_idx,
                        'matched': movie['title']
                    }
    
    return {'error': f'No item found matching: {name}'}


def confirm_selection(tree: list, match_info: dict) -> bool:
    """Show partial tree and wait for user confirmation.
    
    Returns True if confirmed, False if aborted.
    """
    print(f"\n{'='*60}", file=sys.stderr)
    print("请确认以下选择:", file=sys.stderr)
    print(build_partial_tree_display(tree, match_info), file=sys.stderr)
    print(f"\n确认选项: y / Y / Yes / yes / 确认 / 是 / 好 / 下载", file=sys.stderr)
    print("输入其他内容或按ESC重新输入", file=sys.stderr)
    
    esc_count = 0
    while True:
        response = read_with_esc("\n请输入确认: ")
        
        if response == 'ESC':
            esc_count += 1
            print(f"\nWARNING ESC 检测到 (第{esc_count}次) - 请重新输入", file=sys.stderr)
            if esc_count >= 3:
                print("\nERROR 连续3次ESC，中止任务", file=sys.stderr)
                return False
            continue
        
        if response.lower() in CONFIRM_KEYWORDS:
            print("\nINFO 已确认，开始下载...", file=sys.stderr)
            return True
        
        print("\nWARNING 无效确认，请重新输入", file=sys.stderr)


def get_movies_for_selection(tree: list, selection: str) -> tuple:
    """Get list of movie dicts for a selection.
    
    Args:
        tree: The category tree
        selection: Selection string (number, 'all', or name)
    
    Returns:
        (movies_list, error_message)
        If error_message is not None, movies_list is empty
    """
    # Check for 'all'
    if selection.lower().strip() == 'all':
        movies = []
        for category in tree:
            for section in category['sections']:
                movies.extend(section.get('example_movies', []))
        return movies, None
    
    # Try numeric parsing
    result = parse_selection(selection, tree)
    if 'error' in result:
        return [], result['error']
    
    return result.get('movies', []), None


def _prompt_selection(tree: list, level: str = "root", selection_stack: list = None) -> str:
    """Prompt user for selection at the given level.
    
    Args:
        tree: Category tree
        level: Current level ('root', 'section', 'movie')
        selection_stack: Stack of previous selections for navigation
    
    Returns:
        Selection string or 'BACK' to go to previous level
    """
    if selection_stack is None:
        selection_stack = []
    
    while True:
        if level == "root":
            print(f"\n{'='*60}", file=sys.stderr)
            print("发现以下类目:", file=sys.stderr)
            print(build_tree_display(tree), file=sys.stderr)
            print(f"\n选择方式:", file=sys.stderr)
            print("  - 单个电影: 1.1.1", file=sys.stderr)
            print("  - 单个 Section: 1.1", file=sys.stderr)
            print("  - 单个类目: 1", file=sys.stderr)
            print("  - 全部: all", file=sys.stderr)
            print("  - 名称搜索: 输入类目/Section/电影名称", file=sys.stderr)
            print("\n按 ESC 可重新输入 (连续3次ESC退出)", file=sys.stderr)
        elif level == "section":
            cat_idx, sec_idx = selection_stack[-1]
            cat = tree[cat_idx]
            sec = cat['sections'][sec_idx]
            sec_name = sec.get('title', sec.get('name', 'Unknown'))
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"已选择 Section: {cat['name']} → {sec_name}", file=sys.stderr)
            print(f"\n请选择电影编号 (如 1, 1.3, 1.5-10, all, r返回上级, n取消):", file=sys.stderr)
        elif level == "movie":
            print(f"\n{'='*60}", file=sys.stderr)
            print("请选择操作:", file=sys.stderr)
            print("  - y: 确认开始下载", file=sys.stderr)
            print("  - n: 取消返回上级", file=sys.stderr)
            print("  - r: 返回上一级重新选择", file=sys.stderr)
        
        if level == "root":
            prompt = "\n请输入选择: "
        elif level == "section":
            prompt = "\n请输入选择: "
        elif level == "movie":
            prompt = "\n请选择 (y/n/r): "
        
        selection = read_with_esc(prompt)
        
        if selection == 'ESC':
            esc_count = 0
            while True:
                confirm = read_with_esc("\n确认退出? (y/n): ")
                if confirm.lower() in ('y', 'yes', '确认', '是', '好', '下载'):
                    print("INFO 退出程序", file=sys.stderr)
                    sys.exit(0)
                elif confirm.lower() in ('n', '不', '不需要', '不用'):
                    break
                print("WARNING 无效输入", file=sys.stderr)
            continue
        
        if not selection:
            print("\nWARNING 空输入，请重新输入", file=sys.stderr)
            continue
        
        # Handle 'r' (return to previous level)
        if selection.lower().strip() == 'r':
            if len(selection_stack) > 0:
                return 'BACK'
            else:
                print("WARNING 已在最顶层，无法返回", file=sys.stderr)
                continue
        
        return selection


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


def _fetch_category_movies(page, cat: dict, cookies: list) -> list:
    """Fetch ALL movies from a category by fetching each section.
    
    Uses shared page object. Always uses fetch_section_movies(), never falls back to example_movies.
    
    Args:
        page: Playwright page object (shared browser context)
        cat: Category dict with 'sections' key
        cookies: Playwright cookies list
    
    Returns:
        List of all movie dicts from the category
    """
    all_movies = []
    
    for sec in cat['sections']:
        sec_name = sec.get('title', sec.get('name', 'Unknown'))
        
        # Navigate to section page and scroll to get all movies
        section_url = sec.get('section_href')
        if section_url:
            print(f"  INFO 爬取 section: {sec_name}", file=sys.stderr)
            section_movies = fetch_section_movies(page, section_url, cookies)
        else:
            print(f"  WARNING 没有 section URL，跳过: {sec_name}", file=sys.stderr)
        
        # Add section info to each movie
        for m in section_movies:
            m['_section'] = sec_name
        all_movies.extend(section_movies)
    
    return all_movies


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
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        # Login
        print("INFO Logging in...", file=sys.stderr)
        login_result = login_prime_video(page, email, password)
        if not login_result['success']:
            print("ERROR Login failed", file=sys.stderr)
            sys.exit(1)
        cookies = login_result['cookies']
        
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
                
                selection = read_with_esc("\n请输入选择: ")
                if selection == 'ESC':
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
                    all_movies = []
                    for cat_idx, cat in enumerate(categories):
                        print(f"  INFO 获取类目: {cat['name']}", file=sys.stderr)
                        sections = extract_sections_from_category(page, cat['href'], cookies)
                        for sec_idx, sec in enumerate(sections):
                            if sec.get('href'):
                                movies = fetch_section_movies(page, sec['href'], cookies)
                                for m in movies:
                                    m['_category'] = cat['name']
                                    m['_section'] = sec['title']
                                all_movies.extend(movies)
                    
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
                    all_movies = []
                    for cat in selected_cats:
                        cat_name = cat['name']
                        cat_href = cat['href']
                        print(f"  INFO 获取类目: {cat_name}", file=sys.stderr)
                        secs = extract_sections_from_category(page, cat_href, cookies)
                        for sec in secs:
                            if sec.get('href'):
                                movies = fetch_section_movies(page, sec['href'], cookies)
                                for m in movies:
                                    m['_category'] = cat_name
                                    m['_section'] = sec['title']
                                all_movies.extend(movies)
                    
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
                    has_url = sec.get('href') and sec['href'].startswith('http')
                    print(f"  {i+1}. {sec['title']} {'[URL] ' if has_url else '[NO URL]'}", file=sys.stderr)
                
                print(f"\n选择方式:", file=sys.stderr)
                print("  - a/all: 下载此类目下所有 sections 的所有电影", file=sys.stderr)
                print("  - s/sec/section/sections: 查看 sections 列表", file=sys.stderr)
                print("  - 数字 (如 1, 1-3, 1,3,5): 进入该 section / 选择多个 section", file=sys.stderr)
                print("  - b/back: 返回类目选择", file=sys.stderr)
                
                selection = read_with_esc("\n请输入选择: ")
                if selection == 'ESC':
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
                    all_movies = []
                    for sec_idx, sec in enumerate(sections):
                        if sec.get('href'):
                            print(f"  INFO 获取 section: {sec['title']}", file=sys.stderr)
                            movies = fetch_section_movies(page, sec['href'], cookies)
                            for m in movies:
                                m['_category'] = cat_name
                                m['_section'] = sec['title']
                            all_movies.extend(movies)
                    
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
                    all_movies = []
                    for sec in selected_secs:
                        sec_name = sec['title']
                        sec_href = sec.get('href')
                        if sec_href:
                            movies = fetch_section_movies(page, sec_href, cookies)
                            for m in movies:
                                m['_category'] = cat_name
                                m['_section'] = sec_name
                            all_movies.extend(movies)
                    
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
                
                selection = read_with_esc("\n请输入选择: ")
                if selection == 'ESC':
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
    """Download subtitles for a list of movies.
    
    Args:
        movies: List of movie dicts (each has 'title' and 'url')
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
    
    print(f"\nINFO 开始下载 {len(movies)} 个电影的字幕...", file=sys.stderr)
    results = []
    
    for i, movie in enumerate(movies):
        print(f"\n{'='*60}", file=sys.stderr)
        movie_title = movie.get('title', '')
        # Use movie's own section info if available (for category downloads)
        movie_section = movie.get('_section', section)
        print(f"INFO 处理电影 {i+1}/{len(movies)}: {movie_title}", file=sys.stderr)
        result = extract_movie_subtitles(
            page, movie['url'],
            movie_title=movie_title,
            category=category,
            section=movie_section
        )
        if DEBUG_MODE:
            print(f"INFO 电影结果: {json.dumps(result, indent=2, ensure_ascii=False)}", file=sys.stderr)
        results.append({
            'title': movie_title,
            'category': category,
            'section': movie_section,
            'success': result.get('subtitles_saved', 0) > 0,
            'subtitles_saved': result.get('subtitles_saved', 0),
            'total_subtitle_types': result.get('total_subtitle_types', 0),
            'filtered_subtitle_types': result.get('filtered_subtitle_types', 0),
            'success_langs': result.get('success_langs', []),
            'failed_langs': result.get('failed_langs', []),
        })
        
        # Collect failed movies for retry
        if not result.get('subtitles_saved', 0) > 0:
            failed_movies.append({
                'url': movie['url'],
                'title': movie_title,
                'category': category,
                'section': movie_section,
                'error': result.get('error', 'unknown'),
            })
    
    # Retry failed movies: 3 attempts each
    if failed_movies:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"INFO 第一轮有 {len(failed_movies)} 个电影失败，开始重试（最多3次）...", file=sys.stderr)
        
        retry_remaining = []
        for fm in failed_movies:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"INFO 重试: {fm['title']} (attempt 1/3)", file=sys.stderr)
            
            for attempt in range(3):
                result = extract_movie_subtitles(
                    page, fm['url'],
                    movie_title=fm['title'],
                    category=fm['category'],
                    section=fm['section']
                )
                if result.get('subtitles_saved', 0) > 0:
                    print(f"INFO 重试成功: {fm['title']} (attempt {attempt+1}/3)", file=sys.stderr)
                    results.append({
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
                    remaining = 2 - attempt
                    if remaining > 0:
                        print(f"INFO 重试失败，还有 {remaining} 次机会: {fm['title']}", file=sys.stderr)
            else:
                # All 3 attempts failed
                retry_remaining.append({
                    'url': fm['url'],
                    'title': fm['title'],
                    'category': fm['category'],
                    'section': fm['section'],
                    'error': result.get('error', 'unknown'),
                })
                print(f"INFO 重试3次全部失败: {fm['title']}", file=sys.stderr)
        
        # Final retry round: 3 more attempts for remaining failures
        if retry_remaining:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"INFO 最终重试: {len(retry_remaining)} 个电影仍失败，再试3次...", file=sys.stderr)
            
            final_remaining = []
            for fm in retry_remaining:
                print(f"\n{'='*60}", file=sys.stderr)
                print(f"INFO 最终重试: {fm['title']} (attempt 1/3)", file=sys.stderr)
                
                for attempt in range(3):
                    result = extract_movie_subtitles(
                        page, fm['url'],
                        movie_title=fm['title'],
                        category=fm['category'],
                        section=fm['section']
                    )
                    if result.get('subtitles_saved', 0) > 0:
                        print(f"INFO 最终重试成功: {fm['title']} (attempt {attempt+1}/3)", file=sys.stderr)
                        results.append({
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
                        remaining = 2 - attempt
                        if remaining > 0:
                            print(f"INFO 重试失败，还有 {remaining} 次机会: {fm['title']}", file=sys.stderr)
                else:
                    final_remaining.append(fm)
                    print(f"INFO 最终重试3次全部失败: {fm['title']}", file=sys.stderr)
            
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
    
    Groups by category -> section, showing only successful downloads.
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
        grouped[cat][sec].append(r['title'])
    
    if not grouped:
        print("\nINFO 没有成功下载任何字幕", file=sys.stderr)
        return
    
    total = sum(len(movies) for cats in grouped.values() for movies in cats.values())
    
    print(f"\n{'='*60}", file=sys.stderr)
    print("下载完成总结", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"总电影数: {total}", file=sys.stderr)
    
    for cat in sorted(grouped.keys()):
        print(f"\n[{cat}]", file=sys.stderr)
        for sec in sorted(grouped[cat].keys()):
            movies = grouped[cat][sec]
            print(f"  [{sec}]", file=sys.stderr)
            for movie in movies:
                print(f"    - {movie} ✓", file=sys.stderr)
    
    print(f"\n{'='*60}", file=sys.stderr)


if __name__ == "__main__":
    main()
