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


def login_prime_video(email: str, password: str, headless: bool = False) -> dict:
    """Login to Prime Video and extract cookies."""
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


def extract_category_tree(cookies: list, headless: bool = False) -> list:
    """Navigate to Prime Video and extract full category → section → example movie tree.
    
    Returns a list of categories, each containing:
    {
        'name': 'Best of India',
        'sections': [
            {
                'name': 'Movies in Tamil',
                'example_movies': [  # 3-5 example movies for display only
                    {'title': 'Bigil', 'url': 'https://www.primevideo.com/detail/...'},
                    ...
                ],
                'see_more_href': 'https://www.primevideo.com/browse/...'
            },
            ...
        ]
    }
    """
    tree = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        
        try:
            print("INFO Navigating to Prime Video homepage...", file=sys.stderr)
            page.goto("https://www.primevideo.com", timeout=30000)
            time.sleep(5)
            
            # Step 1: Find ALL category links on the homepage
            # This includes both genres (/genre/...) and featured collections (/collection/...)
            print("INFO Extracting all categories from homepage...", file=sys.stderr)
            
            category_links_js = page.evaluate('''() => {
                const categories = [];
                const seen = new Set();
                
                function getDirectText(el) {
                    let text = "";
                    for (const node of el.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
                    }
                    return text.trim();
                }
                
                // Find all links that lead to genre or collection pages
                const allLinks = document.querySelectorAll('a');
                for (const link of allLinks) {
                    const href = link.getAttribute('href');
                    if (!href) continue;
                    
                    // Match /genre/... or /collection/... URLs
                    if (href.includes('/genre/') || href.includes('/collection/')) {
                        const text = getDirectText(link).trim();
                        if (text && text.length > 2 && text.length < 100 && !seen.has(text)) {
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
            
            if not category_links_js:
                print("ERROR No categories found", file=sys.stderr)
                return tree
            
            # Step 2: For each category, extract sections with example movies
            for cat_idx, category in enumerate(category_links_js):
                print(f"\nINFO [{cat_idx+1}/{len(category_links_js)}] Extracting: {category['name']}", file=sys.stderr)
                
                cat_data = {'name': category['name'], 'sections': []}
                
                try:
                    page.goto(category['href'], timeout=30000)
                    time.sleep(8)
                except Exception as e:
                    print(f"WARNING Failed to navigate to {category['name']}: {e}", file=sys.stderr)
                    continue
                
                # Extract sections with 3-5 example movies each
                sections_js = page.evaluate('''() => {
                    const sections = [];
                    const rawContainers = document.querySelectorAll('[class*="row"], [class*="carousel"]');
                    const seen = new Set();
                    
                    for (const container of rawContainers) {
                        // Check if this container has movie links
                        const movieLinks = container.querySelectorAll("a[href*='/detail/']");
                        if (movieLinks.length === 0) continue;
                        
                        // Find section title from nearest h2/h3
                        let title = "";
                        let prev = container.previousElementSibling;
                        while (prev && !title) {
                            const titleEl = prev.querySelector("h2, h3");
                            if (titleEl) {
                                for (const node of titleEl.childNodes) {
                                    if (node.nodeType === Node.TEXT_NODE) title += node.textContent;
                                }
                                title = title.trim();
                            }
                            prev = prev.previousElementSibling;
                        }
                        
                        // Fallback: check inside container
                        if (!title) {
                            const innerTitle = container.querySelector("[class*='title'], [class*='heading']");
                            if (innerTitle) {
                                for (const node of innerTitle.childNodes) {
                                    if (node.nodeType === Node.TEXT_NODE) title += node.textContent;
                                }
                                title = title.trim();
                            }
                        }
                        
                        if (!title || title.length < 2) continue;
                        if (seen.has(title)) continue;
                        seen.add(title);
                        
                        // Find "See more" link
                        let seeMoreHref = null;
                        for (const link of container.querySelectorAll("a")) {
                            if (link.textContent.includes("See more") || link.textContent.includes("See More")) {
                                seeMoreHref = link.getAttribute("href");
                                break;
                            }
                        }
                        
                        // Extract 3-5 example movies
                        const exampleMovies = [];
                        const maxExamples = Math.min(5, movieLinks.length);
                        for (let i = 0; i < maxExamples; i++) {
                            const link = movieLinks[i];
                            const href = link.getAttribute("href");
                            let movieTitle = "";
                            // Try to get title from data attributes or surrounding elements
                            const titleAttr = link.getAttribute("aria-label") || link.getAttribute("data-tracker-title");
                            if (titleAttr) {
                                movieTitle = titleAttr.trim();
                            } else {
                                // Get text from the link itself or child elements
                                for (const node of link.childNodes) {
                                    if (node.nodeType === Node.TEXT_NODE) movieTitle += node.textContent;
                                }
                                movieTitle = movieTitle.trim();
                            }
                            
                            if (movieTitle && movieTitle.length > 2 && movieTitle.length < 100) {
                                exampleMovies.push({
                                    title: movieTitle,
                                    url: href.startsWith('http') ? href : 'https://www.primevideo.com' + href
                                });
                            }
                        }
                        
                        if (exampleMovies.length > 0) {
                            sections.push({
                                title: title,
                                seeMoreHref: seeMoreHref,
                                exampleMovies: exampleMovies
                            });
                        }
                    }
                    
                    return sections;
                }''')
                
                print(f"INFO   Found {len(sections_js)} sections", file=sys.stderr)
                
                for sec in sections_js:
                    sec_data = {
                        'name': sec['title'],
                        'example_movies': sec.get('exampleMovies', []),
                        'see_more_href': sec.get('seeMoreHref')
                    }
                    cat_data['sections'].append(sec_data)
                    
                    example_str = ", ".join(m['title'] for m in sec_data['example_movies'][:3])
                    print(f"    - {sec_data['name']} (examples: {example_str})", file=sys.stderr)
                
                tree.append(cat_data)
                print(f"INFO   Done: {len(cat_data['sections'])} sections", file=sys.stderr)
        
        finally:
            browser.close()
    
    print(f"INFO Total categories extracted: {len(tree)}", file=sys.stderr)
    return tree


def extract_movie_subtitles(movie_url: str, cookies: list, headless: bool = False) -> dict:
    """Extract subtitles from a Prime Video movie using playback envelope API.
    
    Returns dict with keys: 'title', 'tamil', 'english', 'has_dual_subtitles'
    """
    result = {
        'title': None,
        'tamil': None,
        'english': None,
        'has_dual_subtitles': False,
        'error': None,
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
                print(f"INFO Fetched subtitle (TTML2): {caption_count} captions from {url[:100]}", file=sys.stderr)
                return srt
            else:
                print(f"WARNING Failed to parse TTML2 content", file=sys.stderr)
                return None
        except Exception as e:
            print(f"WARNING Error fetching subtitle: {e}", file=sys.stderr)
        return None
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        
        try:
            # Set up console logging AND response interception
            console_msgs = []
            webspa_responses = []  # Store responses from x-requested-with: WebSPA requests
            
            def on_console(msg):
                console_msgs.append(msg.text)
                print(f"DEBUG Console: {msg.text}", file=sys.stderr)
            page.on('console', on_console)
            
            def on_response(response):
                url = response.url
                # Capture enrichItemMetadata response body
                if 'enrichItemMetadata' in url and response.status == 200:
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
                
                if(!result.envelope) {
                    result.error = "Could not find playbackEnvelope in actions";
                    result.actions = actions.map(a => ({
                        id: a.id,
                        source: a.source,
                        hasPrimaryActions: !!a.extracted.primaryActions,
                        hasPlaybackActions: !!a.extracted.playbackActions,
                        primaryActionsCount: a.extracted.primaryActions?.length || 0
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
                result['error'] = init_result['error']
                return result
            
            envelope = init_result['envelope']
            envelope_source = init_result['envelopeSource']
            movie_url = init_result['movieUrl']
            
            print(f"INFO Found playbackEnvelope from {envelope_source}", file=sys.stderr)
            print(f"INFO Envelope preview: {envelope[:100] if isinstance(envelope, str) else 'not a string'}...", file=sys.stderr)
            print(f"INFO Movie URL: {movie_url}", file=sys.stderr)
            
            # Step 5: POST to GetVodPlaybackResources with timedTextUrlsRequest
            # Use hardcoded device params (same as the page uses)
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
            print(f"INFO Device params: {device_params}", file=sys.stderr)
            
            sub_info_result = page.evaluate(
                '''async ({ envelope, deviceParams, movieUrl }) => {
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
                        
                        console.log('DEBUG GVod URL:', url);
                        
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
                        
                        console.log('DEBUG GVod status:', response.status);
                        console.log('DEBUG GVod contentType:', contentType);
                        console.log('DEBUG GVod body (first 2000):', text.substring(0, 2000));
                        
                        let parsed = null;
                        if(contentType.includes('application/json')) {
                            try {
                                parsed = JSON.parse(text);
                                console.log('DEBUG GVod parsed timedTextUrls:', JSON.stringify(parsed.timedTextUrls, null, 2).substring(0, 2000));
                            } catch(e) {
                                console.log('DEBUG GVod JSON parse error:', e.message);
                            }
                        }
                        
                        return {
                            status: response.status,
                            contentType: contentType,
                            bodyPreview: text.substring(0, 3000),
                            parsed: parsed
                        };
                    } catch(e) {
                        console.log('DEBUG GVod error:', e.message);
                        console.log('DEBUG GVod error stack:', e.stack);
                        return { error: e.message || String(e) };
                    }
                }''',
                {'envelope': envelope, 'deviceParams': device_params, 'movieUrl': movie_url}
            )
            
            print(f"INFO Subtitle API result: status={sub_info_result.get('status')}, contentType={sub_info_result.get('contentType')}", file=sys.stderr)
            
            if sub_info_result.get('parsed'):
                parsed = sub_info_result['parsed']
                # Check for timedTextUrls.result (matching userscript's getSubInfo return)
                timed_text_urls = None
                if parsed.get('timedTextUrls') and parsed['timedTextUrls'].get('result'):
                    timed_text_urls = parsed['timedTextUrls']['result']
                    subtitle_urls = timed_text_urls.get('subtitleUrls', [])
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
            
            print(f"INFO Filtered to {len(filtered_subtitles)} subtitles (types={ALLOWED_TYPES})", file=sys.stderr)
            
            if not filtered_subtitles:
                print(f"WARNING No target subtitles found for {result.get('title', 'unknown movie')}", file=sys.stderr)
                return result
            
            # Download and save each subtitle
            import os
            movie_name = result.get('title', 'movie').replace('/', '_').replace('\\', '_').replace(':', '.')
            output_dir = os.path.join('data', 'subtitles', movie_name)
            os.makedirs(output_dir, exist_ok=True)
            
            saved_count = 0
            for sub in filtered_subtitles:
                srt_content = fetch_subtitle(sub['url'])
                if not srt_content:
                    print(f"WARNING Failed to fetch subtitle: {sub['lang_code']} ({sub['type']})", file=sys.stderr)
                    continue
                
                filename = build_filename(movie_name, sub['lang_code'], sub['type'])
                filepath = os.path.join(output_dir, f"{filename}.srt")
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(srt_content)
                
                caption_count = srt_content.count('\n\n')
                print(f"INFO Saved: {filepath} ({caption_count} captions, type={sub['type']})", file=sys.stderr)
                saved_count += 1
            
            result['subtitles_saved'] = saved_count
            result['subtitle_dir'] = output_dir
            print(f"INFO Total subtitles saved: {saved_count} to {output_dir}", file=sys.stderr)
        
        finally:
            browser.close()
    
    return result


def fetch_section_movies(section_url: str, cookies: list, headless: bool = False) -> list:
    """Navigate to section page, scroll to bottom (infinite load), and extract all movies.
    
    Args:
        section_url: The 'See more' URL for the section
        cookies: Playwright cookies list
        headless: Whether to run headless
    
    Returns:
        List of movie dicts: [{'title': '...', 'url': '...'}, ...]
    """
    all_movies = []
    seen_urls = set()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        
        try:
            print(f"INFO Navigating to section: {section_url[:100]}...", file=sys.stderr)
            page.goto(section_url, timeout=30000)
            time.sleep(5)
            
            # Scroll to bottom and wait for infinite loading
            print("INFO Scrolling to bottom and waiting for infinite loading...", file=sys.stderr)
            prev_count = 0
            scroll_count = 0
            max_scrolls = 30  # Safety limit
            
            while scroll_count < max_scrolls:
                # Scroll down by viewport height
                page.evaluate('window.scrollBy(0, window.innerHeight)')
                time.sleep(1.5)  # Wait for content to load
                
                # Count current movies
                current_movies = page.evaluate('''() => {
                    const links = document.querySelectorAll("a[href*='/detail/']");
                    return links.length;
                }''')
                
                if current_movies == prev_count:
                    # No new movies loaded, try one more time
                    time.sleep(2)
                    after_wait = page.evaluate('''() => {
                        const links = document.querySelectorAll("a[href*='/detail/']");
                        return links.length;
                    }''')
                    if after_wait == current_movies:
                        print(f"INFO Infinite loading complete: {current_movies} movies found", file=sys.stderr)
                        break
                
                prev_count = current_movies
                scroll_count += 1
            
            # Extract all movies
            print("INFO Extracting all movies...", file=sys.stderr)
            all_movies = page.evaluate('''() => {
                const movies = [];
                const seen = new Set();
                const links = document.querySelectorAll("a[href*='/detail/']");
                
                for (const link of links) {
                    const href = link.getAttribute("href");
                    if (!href || seen.has(href)) continue;
                    
                    let movieTitle = "";
                    const titleAttr = link.getAttribute("aria-label") || link.getAttribute("data-tracker-title");
                    if (titleAttr) {
                        movieTitle = titleAttr.trim();
                    } else {
                        for (const node of link.childNodes) {
                            if (node.nodeType === Node.TEXT_NODE) movieTitle += node.textContent;
                        }
                        movieTitle = movieTitle.trim();
                    }
                    
                    if (movieTitle && movieTitle.length > 2 && movieTitle.length < 100) {
                        seen.add(href);
                        movies.push({
                            title: movieTitle,
                            url: href.startsWith('http') ? href : 'https://www.primevideo.com' + href
                        });
                    }
                }
                return movies;
            }''')
            
            print(f"INFO Extracted {len(all_movies)} movies from section", file=sys.stderr)
        
        finally:
            browser.close()
    
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
       1.1. Movies in Tamil        ← 示例: Bigil, Coolie, Varisu
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
            examples = section.get('example_movies', [])
            example_str = ""
            if examples:
                example_str = "  ← 示例: " + ", ".join(m['title'] for m in examples[:3])
            lines.append(f"  {cat_num}.{sec_num}. {section['name']}{example_str}")
    
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
            lines.append(f"  {cat_num}.{sec_num}. {section['name']}")
    
    elif match_info['type'] == 'section':
        cat = tree[match_info['cat_idx']]
        cat_num = match_info['cat_idx'] + 1
        sec = cat['sections'][match_info['sec_idx']]
        sec_num = match_info['sec_idx'] + 1
        lines.append(f"{cat_num}. {cat['name']}")
        lines.append(f"  {cat_num}.{sec_num}. {sec['name']}")
    
    elif match_info['type'] == 'movie':
        cat = tree[match_info['cat_idx']]
        cat_num = match_info['cat_idx'] + 1
        sec = cat['sections'][match_info['sec_idx']]
        sec_num = match_info['sec_idx'] + 1
        mov = sec['example_movies'][match_info['mov_idx']]
        mov_num = match_info['mov_idx'] + 1
        lines.append(f"{cat_num}. {cat['name']}")
        lines.append(f"  {cat_num}.{sec_num}. {sec['name']}")
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
            movies.extend(section['movies'])
        
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
        
        movies = tree[cat_idx]['sections'][sec_idx]['movies']
        
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
        if mov_idx < 0 or mov_idx >= len(tree[cat_idx]['sections'][sec_idx]['movies']):
            return {'error': f'Invalid movie index: {parts[2]}'}
        
        movie = tree[cat_idx]['sections'][sec_idx]['movies'][mov_idx]
        
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
            if name_lower in section['name'].lower():
                return {
                    'type': 'section',
                    'cat_idx': cat_idx,
                    'sec_idx': sec_idx,
                    'mov_idx': None,
                    'matched': section['name']
                }
    
    # Search for movie
    for cat_idx, category in enumerate(tree):
        for sec_idx, section in enumerate(category['sections']):
            for mov_idx, movie in enumerate(section['movies']):
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
                movies.extend(section['movies'])
        return movies, None
    
    # Try numeric parsing
    result = parse_selection(selection, tree)
    if 'error' in result:
        return [], result['error']
    
    return result.get('movies', []), None


def main():
    """Main function with interactive selection."""
    email = "xing.c@hotmail.com"
    password = "789qweasd"
    
    # Login
    print("INFO Logging in...", file=sys.stderr)
    login_result = login_prime_video(email, password)
    if not login_result['success']:
        print("ERROR Login failed", file=sys.stderr)
        sys.exit(1)
    cookies = login_result['cookies']
    
    # Extract category tree
    print("\nINFO Extracting category tree from Prime Video...", file=sys.stderr)
    tree = extract_category_tree(cookies)
    
    if not tree:
        print("ERROR No categories found", file=sys.stderr)
        sys.exit(1)
    
    # Display tree
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
    
    # Interactive selection loop
    esc_count = 0
    while True:
        selection = read_with_esc("\n请输入选择: ")
        
        if selection == 'ESC':
            esc_count += 1
            print(f"\nWARNING ESC 检测到 (第{esc_count}次) - 请重新输入", file=sys.stderr)
            if esc_count >= 3:
                print("\nERROR 连续3次ESC，退出程序", file=sys.stderr)
                sys.exit(0)
            continue
        
        if not selection:
            print("\nWARNING 空输入，请重新输入", file=sys.stderr)
            continue
        
        # Handle 'all'
        if selection.lower().strip() == 'all':
            print("\nINFO 下载全部 category 下的所有电影字幕...", file=sys.stderr)
            all_movies = []
            for cat in tree:
                for sec in cat['sections']:
                    if sec.get('see_more_href'):
                        section_movies = fetch_section_movies(sec['see_more_href'], cookies)
                        all_movies.extend(section_movies)
            
            if all_movies:
                download_movies(all_movies, cookies, "all")
            else:
                print("WARNING 没有找到电影", file=sys.stderr)
            continue
        
        # Try numeric parsing
        result = parse_selection(selection, tree)
        
        if 'error' in result:
            # Try name-based search
            name_result = find_items_by_name(tree, selection)
            if 'error' in name_result:
                print(f"\nWARNING 未找到匹配项: {selection}", file=sys.stderr)
                continue
            
            # Resolve to selection
            if name_result['type'] == 'movie':
                selection_num = f"{name_result['cat_idx']+1}.{name_result['sec_idx']+1}.{name_result['mov_idx']+1}"
                result = parse_selection(selection_num, tree)
            elif name_result['type'] == 'section':
                selection_num = f"{name_result['cat_idx']+1}.{name_result['sec_idx']+1}"
                result = parse_selection(selection_num, tree)
            else:
                selection_num = f"{name_result['cat_idx']+1}"
                result = parse_selection(selection_num, tree)
            
            if 'error' in result:
                print(f"\nWARNING 选择解析失败", file=sys.stderr)
                continue
        
        # Handle based on selection type
        sel_type = result.get('type')
        cat_idx = result.get('cat_idx', -1)
        sec_idx = result.get('sec_idx')
        
        if sel_type == 'movie':
            # Single movie - download directly
            movies = result.get('movies', [])
            if movies:
                download_movies(movies, cookies, "movie")
        
        elif sel_type == 'section':
            # Section - ask if user wants to select specific movies
            cat = tree[cat_idx]
            sec = cat['sections'][sec_idx]
            print(f"\nINFO 已选择 Section: {cat['name']} → {sec['name']}", file=sys.stderr)
            
            # Ask for secondary interaction
            print("\n是否要单独选择某个/某些电影？", file=sys.stderr)
            print("(输入 y/yes/确认/是/好/下载 查看列表，输入 n/no/不/不需要/空 直接下载全部)", file=sys.stderr)
            
            esc_count_sec = 0
            while True:
                answer = read_with_esc("\n请选择: ")
                
                if answer == 'ESC':
                    esc_count_sec += 1
                    print(f"\nWARNING ESC 检测到 (第{esc_count_sec}次) - 请重新输入", file=sys.stderr)
                    if esc_count_sec >= 3:
                        print("\nERROR 连续3次ESC，退出程序", file=sys.stderr)
                        sys.exit(0)
                    continue
                
                if not answer:
                    # Empty = download all
                    answer = 'no'
                    break
                
                if answer.lower() in ('y', 'yes', '确认', '是', '好', '下载'):
                    # Fetch full movie list
                    if not sec.get('see_more_href'):
                        print("WARNING 该 section 没有 'See more' 链接，直接下载示例电影", file=sys.stderr)
                        movies = sec.get('example_movies', [])
                        download_movies(movies, cookies, "section")
                        break
                    
                    print("\nINFO 正在爬取完整电影列表 (scroll 到底部)...", file=sys.stderr)
                    full_movies = fetch_section_movies(sec['see_more_href'], cookies)
                    
                    if not full_movies:
                        print("WARNING 没有找到电影", file=sys.stderr)
                        break
                    
                    # Show full list
                    print(f"\n{'='*60}", file=sys.stderr)
                    print(f"完整电影列表 (共 {len(full_movies)} 部):", file=sys.stderr)
                    for i, movie in enumerate(full_movies):
                        print(f"  {i+1}. {movie['title']}", file=sys.stderr)
                    
                    print(f"\n请选择电影编号 (如 1, 1.3, 1.5-10, all):", file=sys.stderr)
                    
                    # Get user's movie selection
                    movie_selection = read_with_esc("")
                    if movie_selection == 'ESC':
                        print("\nINFO 退出", file=sys.stderr)
                        break
                    
                    if not movie_selection:
                        # Empty = download all
                        download_movies(full_movies, cookies, "section")
                        break
                    
                    # Parse movie selection
                    if movie_selection.lower().strip() == 'all':
                        download_movies(full_movies, cookies, "section")
                    else:
                        # Parse individual movie indices
                        selected_movies = []
                        for part in movie_selection.split(','):
                            part = part.strip()
                            if '-' in part:
                                start, end = part.split('-', 1)
                                for i in range(int(start), int(end) + 1):
                                    if 0 < i <= len(full_movies):
                                        selected_movies.append(full_movies[i - 1])
                            else:
                                try:
                                    idx = int(part)
                                    if 0 < idx <= len(full_movies):
                                        selected_movies.append(full_movies[idx - 1])
                                except ValueError:
                                    pass
                        
                        if selected_movies:
                            download_movies(selected_movies, cookies, "section")
                        else:
                            print("WARNING 未选择任何电影", file=sys.stderr)
                    break
                
                elif answer.lower() in ('n', 'no', '不', '不需要', '不用'):
                    # Download all movies in section
                    if sec.get('see_more_href'):
                        print("\nINFO 正在爬取完整电影列表...", file=sys.stderr)
                        full_movies = fetch_section_movies(sec['see_more_href'], cookies)
                        download_movies(full_movies, cookies, "section")
                    else:
                        # No see_more link, use example movies
                        movies = sec.get('example_movies', [])
                        download_movies(movies, cookies, "section")
                    break
                else:
                    print("\nWARNING 无效输入，请重新输入", file=sys.stderr)
            continue
        
        elif sel_type == 'category':
            # Category - download all movies in all sections
            cat = tree[cat_idx]
            print(f"\nINFO 下载类目: {cat['name']} 下所有电影字幕...", file=sys.stderr)
            
            all_movies = []
            for sec in cat['sections']:
                if sec.get('see_more_href'):
                    print(f"  INFO 爬取 section: {sec['name']}", file=sys.stderr)
                    section_movies = fetch_section_movies(sec['see_more_href'], cookies)
                    all_movies.extend(section_movies)
                else:
                    # Use example movies
                    all_movies.extend(sec.get('example_movies', []))
            
            if all_movies:
                download_movies(all_movies, cookies, "category")
            else:
                print("WARNING 没有找到电影", file=sys.stderr)
        
        else:
            print(f"\nWARNING 未知选择类型: {sel_type}", file=sys.stderr)
        
        # Ask if user wants to download more
        print("\n是否继续下载更多? (y/n)", file=sys.stderr)
        more = read_with_esc("")
        if more.lower() not in ('y', 'yes', '确认', '是', '好', '下载'):
            print("INFO 退出", file=sys.stderr)
            break


def download_movies(movies: list, cookies: list, context: str = "") -> None:
    """Download subtitles for a list of movies.
    
    Args:
        movies: List of movie dicts
        cookies: Playwright cookies
        context: Context string for logging (category/section/movie)
    """
    if not movies:
        print("WARNING 没有电影可下载", file=sys.stderr)
        return
    
    print(f"\nINFO 开始下载 {len(movies)} 个电影的字幕...", file=sys.stderr)
    success_count = 0
    
    for i, movie in enumerate(movies):
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"INFO 处理电影 {i+1}/{len(movies)}: {movie['title']}", file=sys.stderr)
        result = extract_movie_subtitles(movie['url'], cookies)
        print(f"INFO 电影结果: {json.dumps(result, indent=2, ensure_ascii=False)}", file=sys.stderr)
        if result.get('subtitles_saved', 0) > 0:
            success_count += 1
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"INFO 下载完成: {success_count}/{len(movies)} 个电影成功", file=sys.stderr)


if __name__ == "__main__":
    main()
