#!/usr/bin/env python3
"""Test Prime Video login and navigate to Tamil movies."""

import json
import sys
import time
import requests
from playwright.sync_api import sync_playwright


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


def find_tamil_movies(cookies: list, headless: bool = False) -> list:
    """Navigate to Tamil movies page and extract movie URLs."""
    movie_urls = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        context.add_cookies(cookies)
        page = context.new_page()
        
        try:
            print("INFO Navigating to Prime Video...", file=sys.stderr)
            page.goto("https://www.primevideo.com", timeout=30000)
            time.sleep(5)
            
            # Click on "Best of India" directly
            print("INFO Looking for Best of India...", file=sys.stderr)
            best_of_india = page.query_selector('a:has-text("Best of India")')
            if not best_of_india:
                print("WARNING Could not find Best of India", file=sys.stderr)
                return movie_urls
            
            print("INFO Found Best of India, clicking...", file=sys.stderr)
            best_of_india.evaluate('el => el.click()')
            time.sleep(5)
            
            # Scroll down to find "Movies in Tamil"
            print("INFO Scrolling down to find Movies in Tamil...", file=sys.stderr)
            page.mouse.wheel(0, 2000)
            time.sleep(3)
            
            # Take screenshot for debugging
            page.screenshot(path="temp/prime_video_movies_page.png")
            print("INFO Screenshot saved to temp/prime_video_movies_page.png", file=sys.stderr)
            
            # Get all section titles and their "See more" links
            print("INFO Looking for sections with Tamil movies...", file=sys.stderr)
            sections = page.query_selector_all('[class*="row"], [class*="carousel"], [class*="section"]')
            for i, section in enumerate(sections):
                title = section.query_selector('[class*="title"], [class*="heading"], h2, h3')
                if title:
                    title_text = title.text_content().strip()
                    see_more = section.query_selector('a:has-text("See more")')
                    if see_more:
                        href = see_more.get_attribute('href')
                        print(f"  Section {i}: {title_text} -> See more: {href}", file=sys.stderr)
            
            # Find "Movies in Tamil" section and click on its "See more>"
            print("INFO Looking for Movies in Tamil section...", file=sys.stderr)
            movies_in_tamil = page.query_selector('a:has-text("Movies in Tamil")')
            if not movies_in_tamil:
                # Try finding section title directly
                movies_in_tamil = page.query_selector('[class*="title"]:has-text("Movies in Tamil")')
            if not movies_in_tamil:
                print("WARNING Could not find Movies in Tamil", file=sys.stderr)
                return movie_urls
            
            print("INFO Found Movies in Tamil section", file=sys.stderr)
            
            # Click on "See more>" within the same section using JavaScript
            see_more = movies_in_tamil.evaluate_handle('''el => {
                let parent = el.closest('[class*="row"], [class*="carousel"], [class*="section"]');
                if (!parent) return null;
                let links = parent.querySelectorAll('a');
                for (let link of links) {
                    if (link.textContent.includes('See more')) {
                        return link;
                    }
                }
                return null;
            }''')
            if not see_more:
                print("WARNING Could not find See more in section", file=sys.stderr)
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
    
    return movie_urls


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
    
    def fetch_subtitle(url, lang='unknown'):
        """Fetch subtitle file and parse it."""
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
                return None, None
            
            # Prime Video subtitles are always TTML2
            srt = ttml2_to_srt(content)
            if srt:
                caption_count = srt.count('\n\n')
                print(f"INFO Fetched {lang} subtitle (TTML2): {caption_count} captions from {url[:100]}", file=sys.stderr)
                result[f'{lang}_srt'] = srt
                return lang, [{'text': 'See SRT content in result'}]
            else:
                print(f"WARNING Failed to parse TTML2 content", file=sys.stderr)
                return lang, []
        except Exception as e:
            print(f"WARNING Error fetching subtitle: {e}", file=sys.stderr)
        return None, None
    
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
                        # Store subtitle URLs in result
                        if lang.startswith('ta'):
                            result['tamil_url'] = url
                        elif lang.startswith('en'):
                            result['english_url'] = url
                elif parsed.get('globalError'):
                    print(f"WARNING Global error: {parsed['globalError']}", file=sys.stderr)
                else:
                    print(f"INFO Parsed response (first 500): {json.dumps(parsed, ensure_ascii=False)[:500]}", file=sys.stderr)
            else:
                print(f"INFO Body preview: {sub_info_result.get('bodyPreview', '')[:500]}", file=sys.stderr)
                result['error'] = "No valid subtitle data returned"
            
            # Download subtitles if URLs are available
            if 'tamil_url' in result:
                print(f"INFO Downloading Tamil subtitle...", file=sys.stderr)
                fetch_subtitle(result['tamil_url'], 'ta')
            if 'english_url' in result:
                print(f"INFO Downloading English subtitle...", file=sys.stderr)
                fetch_subtitle(result['english_url'], 'en')
            
            # Check if we have dual subtitles
            has_tamil = 'ta_srt' in result
            has_english = 'en_srt' in result
            if has_tamil and has_english:
                result['has_dual_subtitles'] = True
                print(f"INFO SUCCESS: Found both Tamil and English subtitles!", file=sys.stderr)
                # Save SRT files
                import os
                safe_title = result.get('title', 'movie').replace('/', '_').replace('\\', '_')
                output_dir = 'temp/subtitles'
                os.makedirs(output_dir, exist_ok=True)
                
                tamil_file = os.path.join(output_dir, f"{safe_title}_ta.srt")
                with open(tamil_file, 'w', encoding='utf-8') as f:
                    f.write(result.get('ta_srt', ''))
                print(f"INFO Saved Tamil subtitle to {tamil_file}", file=sys.stderr)
                
                english_file = os.path.join(output_dir, f"{safe_title}_en.srt")
                with open(english_file, 'w', encoding='utf-8') as f:
                    f.write(result.get('en_srt', ''))
                print(f"INFO Saved English subtitle to {english_file}", file=sys.stderr)
            elif has_tamil:
                result['has_dual_subtitles'] = False
                print(f"INFO Found Tamil subtitle only", file=sys.stderr)
            elif has_english:
                result['has_dual_subtitles'] = False
                print(f"INFO Found English subtitle only", file=sys.stderr)
        
        finally:
            browser.close()
    
    return result


def main():
    """Main function for testing Prime Video."""
    email = "xing.c@hotmail.com"
    password = "789qweasd"
    
    # Login
    print("INFO Logging in...", file=sys.stderr)
    login_result = login_prime_video(email, password)
    if not login_result['success']:
        print("ERROR Login failed", file=sys.stderr)
        sys.exit(1)
    cookies = login_result['cookies']
    
    # Navigate to Tamil movies and extract URLs
    movie_urls = find_tamil_movies(cookies)
    print(f"INFO Tamil movie URLs: {json.dumps(movie_urls, indent=2, ensure_ascii=False)}", file=sys.stderr)
    
    # Extract subtitles from each movie (just first 3 for testing)
    for i, url in enumerate(movie_urls[:3]):
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"INFO Processing movie {i+1}/{len(movie_urls[:3])}...", file=sys.stderr)
        result = extract_movie_subtitles(url, cookies)
        print(f"INFO Movie {i+1} result:", file=sys.stderr)
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
