import streamlit as st
import time
import threading
import gc
import json
import os
import uuid
import random
import tempfile
from pathlib import Path
from collections import deque
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

st.set_page_config(
    page_title="FB Auto Tool",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

KEEP_ALIVE_JS = """
<script>
    setInterval(function() { fetch(window.location.href, {method: 'HEAD'}).catch(function(){}); }, 25000);
    setInterval(function() { document.dispatchEvent(new MouseEvent('mousemove', {bubbles: true, clientX: Math.random()*200, clientY: Math.random()*200})); }, 60000);
</script>
"""

custom_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
    * { font-family: 'Poppins', sans-serif; }
    .stApp {
        background-image: url('https://i.postimg.cc/TYhXd0gG/d0a72a8cea5ae4978b21e04a74f0b0ee.jpg');
        background-size: cover; background-position: center; background-attachment: fixed;
    }
    .main .block-container {
        background: rgba(255,255,255,0.08); backdrop-filter: blur(8px);
        border-radius: 12px; padding: 20px; border: 1px solid rgba(255,255,255,0.12);
    }
    .main-header {
        background: rgba(255,255,255,0.1); backdrop-filter: blur(10px);
        padding: 1rem; border-radius: 12px; text-align: center; margin-bottom: 1rem;
    }
    .main-header h1 {
        background: linear-gradient(45deg, #ff6b6b, #4ecdc4);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        font-size: 1.8rem; font-weight: 700; margin: 0;
    }
    .stButton>button {
        background: linear-gradient(45deg, #ff6b6b, #4ecdc4);
        color: white; border: none; border-radius: 8px; padding: 0.6rem 1.5rem;
        font-weight: 600; width: 100%;
    }
    .stTextInput>div>div>input, .stTextArea>div>div>textarea, .stNumberInput>div>div>input {
        background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25);
        border-radius: 8px; color: white; padding: 0.6rem;
    }
    label { color: white !important; font-weight: 500 !important; font-size: 13px !important; }
    .console-box {
        background: rgba(0,0,0,0.6); border: 1px solid rgba(78,205,196,0.5);
        border-radius: 8px; padding: 10px; font-family: 'Courier New', monospace;
        font-size: 11px; color: #00ff88; max-height: 220px; overflow-y: auto;
        min-height: 100px;
    }
    .log-line { padding: 3px 6px; border-left: 2px solid #4ecdc4; margin: 2px 0; background: rgba(0,0,0,0.3); }
    .status-running { background: linear-gradient(135deg, #84fab0, #8fd3f4); padding: 8px; border-radius: 8px; color: white; text-align: center; font-weight: 600; }
    .status-stopped { background: linear-gradient(135deg, #fa709a, #fee140); padding: 8px; border-radius: 8px; color: white; text-align: center; font-weight: 600; }
    .online-indicator {
        display: inline-block; width: 10px; height: 10px; background-color: #00ff00;
        border-radius: 50%; margin-right: 5px; box-shadow: 0 0 5px #00ff00;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0,255,0,0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 5px rgba(0,255,0,0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0,255,0,0); }
    }
    [data-testid="stMetricValue"] { color: #4ecdc4; font-weight: 700; }
    .active-sessions { background: rgba(0,0,0,0.4); border: 1px solid rgba(78,205,196,0.5); border-radius: 10px; padding: 15px; margin-top: 20px; }
    .tab-header { color: white; font-size: 1.1rem; font-weight: 600; margin-bottom: 10px; }
    .info-box { background: rgba(78,205,196,0.15); border: 1px solid rgba(78,205,196,0.4); border-radius: 8px; padding: 10px; color: white; font-size: 12px; margin: 8px 0; }
</style>
"""

st.markdown(custom_css, unsafe_allow_html=True)
st.markdown(KEEP_ALIVE_JS, unsafe_allow_html=True)

SESSIONS_FILE = "sessions_registry.json"
LOGS_DIR = "session_logs"
TEMP_IMAGES_DIR = "temp_images"
MAX_LOGS = 30

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(TEMP_IMAGES_DIR, exist_ok=True)


class Session:
    __slots__ = ['id', 'running', 'count', 'logs', 'idx', 'img_idx', 'driver',
                 'start_time', 'profile_id', 'session_type']

    def __init__(self, sid, session_type='comment'):
        self.id = sid
        self.running = False
        self.count = 0
        self.logs = deque(maxlen=MAX_LOGS)
        self.idx = 0
        self.img_idx = 0
        self.driver = None
        self.start_time = None
        self.profile_id = None
        self.session_type = session_type

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        profile_str = f" {self.profile_id}" if self.profile_id else ""
        log_entry = f"[{ts}]{profile_str} {msg}"
        self.logs.append(log_entry)
        try:
            with open(f"{LOGS_DIR}/{self.id}.log", "a") as f:
                f.write(log_entry + "\n")
        except:
            pass


@st.cache_resource
def get_session_manager():
    return SessionManager()


class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.lock = threading.Lock()
        self._load_registry()

    def _load_registry(self):
        if os.path.exists(SESSIONS_FILE):
            try:
                with open(SESSIONS_FILE, 'r') as f:
                    data = json.load(f)
                    for sid, info in data.items():
                        if sid not in self.sessions:
                            s = Session(sid, info.get('session_type', 'comment'))
                            s.count = info.get('count', 0)
                            s.running = False
                            s.start_time = info.get('start_time')
                            self.sessions[sid] = s
            except:
                pass

    def _save_registry(self):
        try:
            data = {}
            for sid, s in self.sessions.items():
                data[sid] = {
                    'count': s.count,
                    'running': s.running,
                    'start_time': s.start_time,
                    'session_type': s.session_type
                }
            with open(SESSIONS_FILE, 'w') as f:
                json.dump(data, f)
        except:
            pass

    def create_session(self, session_type='comment'):
        with self.lock:
            sid = uuid.uuid4().hex[:8].upper()
            s = Session(sid, session_type)
            self.sessions[sid] = s
            self._save_registry()
            return s

    def get_session(self, sid):
        return self.sessions.get(sid)

    def get_all_sessions(self):
        return list(self.sessions.values())

    def get_active_sessions(self):
        return [s for s in self.sessions.values() if s.running]

    def stop_session(self, sid):
        s = self.sessions.get(sid)
        if s:
            s.running = False
            if s.driver:
                try:
                    s.driver.quit()
                except:
                    pass
                s.driver = None
            self._save_registry()

    def delete_session(self, sid):
        with self.lock:
            s = self.sessions.get(sid)
            if s:
                s.running = False
                if s.driver is not None:
                    try:
                        s.driver.quit()
                    except:
                        pass
                    s.driver = None
                del self.sessions[sid]
                try:
                    os.remove(f"{LOGS_DIR}/{sid}.log")
                except:
                    pass
                self._save_registry()
                gc.collect()

    def get_logs(self, sid, limit=30):
        log_file = f"{LOGS_DIR}/{sid}.log"
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    lines = f.readlines()
                    return lines[-limit:]
            except:
                pass
        s = self.sessions.get(sid)
        if s:
            return list(s.logs)[-limit:]
        return []

    def update_count(self, sid, count):
        s = self.sessions.get(sid)
        if s:
            s.count = count
            self._save_registry()


manager = get_session_manager()


def extract_fb_uid(cookies):
    try:
        cookie_dict = {}
        if cookies:
            for c in cookies.split(';'):
                c = c.strip()
                if c and '=' in c:
                    i = c.find('=')
                    cookie_dict[c[:i].strip()] = c[i + 1:].strip()
        return cookie_dict.get('c_user') or cookie_dict.get('uid') or "Unknown"
    except:
        return "Unknown"


def setup_browser(session):
    session.log('Setting up Chromium browser...')
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-setuid-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--window-size=1920,1080')
    opts.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    )

    for p in ['/usr/bin/chromium', '/usr/bin/chromium-browser',
              '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable']:
        if Path(p).exists():
            opts.binary_location = p
            break

    drv_path = None
    for d in ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver']:
        if Path(d).exists():
            drv_path = d
            break

    from selenium.webdriver.chrome.service import Service
    if drv_path:
        svc = Service(executable_path=drv_path)
        driver = webdriver.Chrome(service=svc, options=opts)
    else:
        driver = webdriver.Chrome(options=opts)

    driver.set_window_size(1920, 1080)
    session.log('Browser ready!')
    return driver


def login_with_cookies(driver, cookies, session):
    session.log('Navigating to Facebook...')
    driver.get('https://www.facebook.com/')
    time.sleep(8)
    if cookies:
        session.log('Adding cookies...')
        for c in cookies.split(';'):
            c = c.strip()
            if c and '=' in c:
                i = c.find('=')
                try:
                    driver.add_cookie({
                        'name': c[:i].strip(),
                        'value': c[i + 1:].strip(),
                        'domain': '.facebook.com',
                        'path': '/'
                    })
                except:
                    pass
        driver.refresh()
        time.sleep(8)


def fetch_profile_name(driver, fb_id):
    try:
        driver.get(f'https://www.facebook.com/{fb_id}')
        time.sleep(8)
        name = driver.execute_script("""
            try {
                let h1 = document.querySelector('h1');
                if (h1) return h1.textContent.trim();
                return 'Unknown';
            } catch(e) { return 'Unknown'; }
        """)
        return name.strip() if name else "Unknown"
    except:
        return "Unknown"


def simulate_human(driver):
    try:
        driver.execute_script("""
            window.scrollBy(0, Math.random() * 200 - 100);
            document.dispatchEvent(new MouseEvent('mousemove', {
                bubbles: true,
                clientX: Math.random() * window.innerWidth,
                clientY: Math.random() * window.innerHeight
            }));
        """)
    except:
        pass


def find_comment_input(driver, session):
    session.log('Finding comment input...')
    time.sleep(10)
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
    except:
        pass

    selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"][data-lexical-editor="true"]',
        'div[aria-label*="comment" i][contenteditable="true"]',
        'div[aria-label*="Comment" i][contenteditable="true"]',
        'div[aria-label*="Write a comment" i][contenteditable="true"]',
        'div[contenteditable="true"][spellcheck="true"]',
        '[role="textbox"][contenteditable="true"]',
        '[contenteditable="true"]'
    ]

    for idx, selector in enumerate(selectors):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                try:
                    is_editable = driver.execute_script("""
                        return arguments[0].contentEditable === 'true' ||
                               arguments[0].tagName === 'TEXTAREA' ||
                               arguments[0].tagName === 'INPUT';
                    """, element)
                    if is_editable:
                        try:
                            element.click()
                            time.sleep(0.5)
                        except:
                            pass
                        session.log(f'Found input with selector #{idx + 1}')
                        return element
                except:
                    continue
        except:
            continue
    return None


def type_text_in_element(driver, element, text):
    driver.execute_script("""
        const element = arguments[0];
        const message = arguments[1];
        element.scrollIntoView({behavior: 'smooth', block: 'center'});
        element.focus();
        element.click();
        if (element.tagName === 'DIV') {
            element.textContent = message;
            element.innerHTML = message;
        } else {
            element.value = message;
        }
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
        element.dispatchEvent(new InputEvent('input', { bubbles: true, data: message }));
    """, element, text)


def press_enter(driver, element):
    driver.execute_script("""
        const element = arguments[0];
        element.focus();
        ['keydown','keypress','keyup'].forEach(function(type) {
            element.dispatchEvent(new KeyboardEvent(type, {
                key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true
            }));
        });
    """, element)


def run_comment_session(session, post_id, cookies, comments_list, prefix, delay):
    retries = 0
    driver = None
    fb_id = extract_fb_uid(cookies)

    while session.running and retries < 10:
        try:
            if driver is None:
                driver = setup_browser(session)
                session.driver = driver
            login_with_cookies(driver, cookies, session)

            profile_name = fetch_profile_name(driver, fb_id)
            session.profile_id = f"📌{profile_name}"
            session.log(f'Profile: {profile_name}')

            session.log('Opening post...')
            if post_id.startswith('http'):
                driver.get(post_id)
            else:
                driver.get(f'https://www.facebook.com/{post_id}')
            time.sleep(15)
            session.log('ID Online - Browser Active!')

            input_not_found_count = 0
            while session.running:
                try:
                    comment_input = find_comment_input(driver, session)
                    if not comment_input:
                        input_not_found_count += 1
                        if input_not_found_count >= 3:
                            session.log('Comment input not found 3 times - stopping')
                            session.running = False
                            break
                        session.log(f'Input not found ({input_not_found_count}/3), refreshing...')
                        driver.get(driver.current_url)
                        time.sleep(15)
                        continue

                    input_not_found_count = 0
                    base_comment = comments_list[session.idx % len(comments_list)]
                    session.idx += 1
                    comment_to_send = f"{prefix} {base_comment}" if prefix else base_comment
                    session.log(f'Typing: {comment_to_send[:30]}...')

                    type_text_in_element(driver, comment_input, comment_to_send)
                    time.sleep(1)
                    session.log('Sending...')
                    press_enter(driver, comment_input)
                    time.sleep(1)

                    session.count += 1
                    manager.update_count(session.id, session.count)
                    session.log(f'Comment #{session.count} sent!')
                    retries = 0

                    jitter = int(delay + random.uniform(-10, 10))
                    jitter = max(10, jitter)
                    session.log(f'Waiting {jitter}s...')
                    for i in range(jitter):
                        if not session.running:
                            break
                        if i > 0 and i % 15 == 0:
                            simulate_human(driver)
                        time.sleep(1)

                    if session.count % 2 == 0:
                        gc.collect()
                        try:
                            driver.execute_script(
                                "window.localStorage.clear(); window.sessionStorage.clear();")
                        except:
                            pass

                except Exception as e:
                    err = str(e)[:60]
                    session.log(f'Error: {err}')
                    if 'session' in err.lower() or 'disconnect' in err.lower():
                        session.log('Restarting browser...')
                        try:
                            driver.quit()
                        except:
                            pass
                        driver = None
                        retries += 1
                        time.sleep(5)
                        break
                    time.sleep(10)

        except Exception as e:
            session.log(f'Fatal: {str(e)[:60]}')
            retries += 1
            try:
                driver.quit()
            except:
                pass
            driver = None
            time.sleep(10)

    session.running = False
    session.log('Stopped.')
    manager._save_registry()
    if driver:
        try:
            driver.quit()
        except:
            pass
    gc.collect()


def open_post_composer(driver, session, target_url):
    session.log('Opening post composer...')
    if target_url.startswith('http'):
        driver.get(target_url)
    else:
        driver.get(f'https://www.facebook.com/{target_url}')
    time.sleep(10)

    composer_selectors = [
        'div[data-pagelet="GroupComposer"] div[role="button"]',
        'div[aria-label*="What\'s on your mind" i]',
        'div[aria-label*="Write something" i]',
        'div[role="button"][tabindex="0"]',
        'span[class*="composer"]',
    ]
    composer_clicked = False
    for sel in composer_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for elem in elems:
                text = (elem.text or '').lower()
                if any(kw in text for kw in ["what's on your mind", "write something", "create post"]):
                    elem.click()
                    time.sleep(3)
                    composer_clicked = True
                    break
            if composer_clicked:
                break
        except:
            continue

    if not composer_clicked:
        try:
            driver.execute_script("""
                var btns = document.querySelectorAll('[role="button"]');
                for(var b of btns) {
                    var t = (b.textContent || '').toLowerCase();
                    if(t.includes("what's on your mind") || t.includes("write something")) {
                        b.click(); break;
                    }
                }
            """)
            time.sleep(3)
        except:
            pass

    text_box = None
    textbox_selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[data-lexical-editor="true"]',
        'div[contenteditable="true"]',
    ]
    for sel in textbox_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                text_box = elems[0]
                break
        except:
            continue

    return text_box


def upload_image_to_post(driver, session, image_path):
    session.log('Attaching image...')
    try:
        photo_btns = driver.find_elements(By.CSS_SELECTOR,
            'div[aria-label*="Photo" i], div[aria-label*="photo" i], '
            'div[data-testid*="photo"], input[type="file"][accept*="image"]'
        )
        file_input = None
        for btn in photo_btns:
            if btn.tag_name.lower() == 'input':
                file_input = btn
                break
        if not file_input:
            driver.execute_script("""
                var inputs = document.querySelectorAll('input[type="file"]');
                for(var inp of inputs) { inp.style.display = 'block'; inp.style.visibility = 'visible'; }
            """)
            inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            if inputs:
                file_input = inputs[0]

        if file_input:
            file_input.send_keys(image_path)
            time.sleep(5)
            session.log('Image attached!')
            return True
        else:
            session.log('Image input not found, skipping image...')
            return False
    except Exception as e:
        session.log(f'Image upload error: {str(e)[:40]}')
        return False


def submit_post(driver, session):
    session.log('Submitting post...')
    submit_selectors = [
        'div[aria-label="Post"][role="button"]',
        'button[type="submit"]',
        'div[role="button"][tabindex="0"]',
    ]
    for sel in submit_selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for elem in elems:
                text = (elem.text or '').strip().lower()
                if text in ['post', 'share now', 'publish']:
                    elem.click()
                    time.sleep(4)
                    session.log('Post submitted!')
                    return True
        except:
            continue

    try:
        clicked = driver.execute_script("""
            var btns = document.querySelectorAll('[role="button"]');
            for(var b of btns) {
                var t = (b.textContent || b.getAttribute('aria-label') || '').toLowerCase().trim();
                if(t === 'post' || t === 'share now' || t === 'publish') {
                    b.click(); return true;
                }
            }
            return false;
        """)
        if clicked:
            time.sleep(4)
            session.log('Post submitted via JS!')
            return True
    except:
        pass

    session.log('Submit button not found!')
    return False


def build_post_text(prefix, mention_ids, line_text):
    parts = []
    if prefix:
        parts.append(prefix.strip())
    if mention_ids:
        mention_parts = []
        for m in mention_ids:
            m = m.strip()
            if not m:
                continue
            if m.startswith('http'):
                mention_parts.append(m)
            else:
                mention_parts.append(f'@{m}' if not m.startswith('@') else m)
        if mention_parts:
            parts.append(' '.join(mention_parts))
    if line_text:
        parts.append(line_text.strip())
    return ' '.join(parts)


def run_post_session(session, target_url, cookies, text_lines, prefix,
                     mention_ids, image_paths, delay):
    retries = 0
    driver = None
    fb_id = extract_fb_uid(cookies)

    while session.running and retries < 10:
        try:
            if driver is None:
                driver = setup_browser(session)
                session.driver = driver
            login_with_cookies(driver, cookies, session)

            profile_name = fetch_profile_name(driver, fb_id)
            session.profile_id = f"📌{profile_name}"
            session.log(f'Profile: {profile_name}')
            session.log('Starting auto-post...')

            while session.running:
                try:
                    line_text = text_lines[session.idx % len(text_lines)] if text_lines else ''
                    session.idx += 1

                    post_text = build_post_text(prefix, mention_ids, line_text)
                    session.log(f'Post text: {post_text[:40]}...')

                    text_box = open_post_composer(driver, session, target_url)

                    if not text_box:
                        session.log('Composer not found, retrying...')
                        time.sleep(10)
                        driver.refresh()
                        time.sleep(10)
                        retries += 1
                        if retries >= 5:
                            session.log('Too many retries - stopping')
                            session.running = False
                        break

                    type_text_in_element(driver, text_box, post_text)
                    time.sleep(2)

                    if image_paths:
                        img_path = image_paths[session.img_idx % len(image_paths)]
                        session.img_idx += 1
                        session.log(f'Using image {session.img_idx}: {Path(img_path).name}')
                        upload_image_to_post(driver, session, img_path)
                        time.sleep(3)

                    submitted = submit_post(driver, session)
                    if submitted:
                        session.count += 1
                        manager.update_count(session.id, session.count)
                        session.log(f'Post #{session.count} done!')
                        retries = 0
                    else:
                        session.log('Post may have failed, continuing...')
                        try:
                            driver.execute_script("document.querySelector('[aria-label=\"Close\"]') && document.querySelector('[aria-label=\"Close\"]').click()")
                        except:
                            pass
                        time.sleep(5)

                    session.log(f'Waiting {delay}s before next post...')
                    for i in range(int(delay)):
                        if not session.running:
                            break
                        if i > 0 and i % 20 == 0:
                            simulate_human(driver)
                        time.sleep(1)

                    if session.count % 3 == 0:
                        gc.collect()

                except Exception as e:
                    err = str(e)[:60]
                    session.log(f'Post error: {err}')
                    if 'session' in err.lower() or 'disconnect' in err.lower():
                        try:
                            driver.quit()
                        except:
                            pass
                        driver = None
                        retries += 1
                        time.sleep(10)
                        break
                    time.sleep(10)

        except Exception as e:
            session.log(f'Fatal: {str(e)[:60]}')
            retries += 1
            try:
                driver.quit()
            except:
                pass
            driver = None
            time.sleep(10)

    session.running = False
    session.log('Stopped.')
    manager._save_registry()
    if driver:
        try:
            driver.quit()
        except:
            pass
    gc.collect()


def save_uploaded_images(uploaded_files, session_id):
    saved = []
    session_img_dir = os.path.join(TEMP_IMAGES_DIR, session_id)
    os.makedirs(session_img_dir, exist_ok=True)
    for i, f in enumerate(uploaded_files):
        ext = Path(f.name).suffix or '.jpg'
        path = os.path.join(session_img_dir, f"{i:03d}{ext}")
        with open(path, 'wb') as fp:
            fp.write(f.read())
        saved.append(os.path.abspath(path))
    return saved


def start_comment_session(session, post_id, cookies, comments, prefix, delay):
    session.running = True
    session.logs = deque(maxlen=MAX_LOGS)
    session.count = 0
    session.idx = 0
    session.start_time = time.strftime("%H:%M:%S")
    try:
        open(f"{LOGS_DIR}/{session.id}.log", 'w').close()
    except:
        pass
    session.log(f'Session {session.id} starting (comment mode)...')
    manager._save_registry()
    comments_list = [c.strip() for c in comments.split('\n') if c.strip()] or ['Nice post!']
    threading.Thread(
        target=run_comment_session,
        args=(session, post_id, cookies, comments_list, prefix, delay),
        daemon=True
    ).start()


def start_post_session(session, target_url, cookies, text_lines, prefix,
                       mention_ids, image_paths, delay):
    session.running = True
    session.logs = deque(maxlen=MAX_LOGS)
    session.count = 0
    session.idx = 0
    session.img_idx = 0
    session.start_time = time.strftime("%H:%M:%S")
    try:
        open(f"{LOGS_DIR}/{session.id}.log", 'w').close()
    except:
        pass
    session.log(f'Session {session.id} starting (auto-post mode)...')
    manager._save_registry()
    threading.Thread(
        target=run_post_session,
        args=(session, target_url, cookies, text_lines, prefix,
              mention_ids, image_paths, delay),
        daemon=True
    ).start()


st.markdown('<div class="main-header"><h1>🚀 FB Auto Tool</h1></div>', unsafe_allow_html=True)

all_sessions = manager.get_all_sessions()
active_sessions = manager.get_active_sessions()
total_actions = sum(s.count for s in all_sessions)

col1, col2, col3 = st.columns(3)
col1.metric("Total Actions", total_actions)
col2.metric("Active Sessions", len(active_sessions))
with col3:
    st.metric("All Sessions", len(all_sessions))

if 'view_session' not in st.session_state:
    st.session_state.view_session = None

st.markdown("---")

if st.session_state.view_session:
    sid = st.session_state.view_session
    session = manager.get_session(sid)
    stype = session.session_type if session else 'comment'
    icon = '📸' if stype == 'post' else '💬'

    st.markdown(f"### {icon} Viewing Session: `{sid}` ({stype.upper()})")

    if session:
        if session.running:
            label = "posts" if stype == 'post' else "comments"
            st.markdown(
                f'<div class="status-running"><span class="online-indicator"></span>'
                f'RUNNING - {session.count} {label}'
                f'{" — " + session.profile_id if session.profile_id else ""}</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown('<div class="status-stopped">STOPPED</div>', unsafe_allow_html=True)

        logs = manager.get_logs(sid, 25)
        if logs:
            logs_html = '<div class="console-box">'
            for log in logs:
                logs_html += f'<div class="log-line">{log.strip()}</div>'
            logs_html += '</div>'
            st.markdown(logs_html, unsafe_allow_html=True)
        else:
            st.markdown('<div class="console-box">No logs yet...</div>', unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if st.button("STOP Session", disabled=not session.running):
                manager.stop_session(sid)
                st.rerun()
        with c2:
            if st.button("Delete Session"):
                manager.delete_session(sid)
                st.session_state.view_session = None
                st.rerun()
        with c3:
            if st.button("Refresh Logs"):
                st.rerun()
        with c4:
            if st.button("Back"):
                st.session_state.view_session = None
                st.rerun()
    else:
        st.error("Session not found")
        if st.button("Back"):
            st.session_state.view_session = None
            st.rerun()

else:
    tab1, tab2 = st.tabs(["💬 Auto Comment", "📸 Auto Post"])

    with tab1:
        st.markdown('<div class="tab-header">Auto Comment on a Post</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            post_id = st.text_input("Post ID/URL", placeholder="https://facebook.com/...", key="c_post_id")
            prefix_c = st.text_input("Prefix (optional)", placeholder="e.g. 🔥 or @tag", key="c_prefix")
            delay_c = st.number_input("Delay (seconds)", 10, 3600, 30, key="c_delay")
        with c2:
            cookies_c = st.text_area("Cookies", height=120, placeholder="Paste your FB cookies here...", key="c_cookies")

        uploaded_comments = st.file_uploader("Upload Comments TXT (one per line)", type=['txt'], key="c_txt")
        if uploaded_comments:
            comments = uploaded_comments.read().decode('utf-8')
            st.success(f"Loaded {len([l for l in comments.split(chr(10)) if l.strip()])} comments")
        else:
            comments = st.text_area("Comments (one per line)", height=80,
                                    placeholder="Nice!\nGreat post!\nLove this!", key="c_comments")

        if st.button("▶ START COMMENT SESSION", use_container_width=True, key="start_comment"):
            if not cookies_c:
                st.error("Cookies required!")
            elif not post_id:
                st.error("Post ID/URL required!")
            elif not comments.strip():
                st.error("Add at least one comment!")
            else:
                new_s = manager.create_session('comment')
                start_comment_session(new_s, post_id, cookies_c, comments, prefix_c, delay_c)
                st.success(f"Comment session started! ID: `{new_s.id}`")
                time.sleep(1)
                st.rerun()

    with tab2:
        st.markdown('<div class="tab-header">Auto Post to Profile / Group / Page</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="info-box">📌 Images cycle one-by-one: Post 1 → Image 1, Post 2 → Image 2, etc. '
            'Text comes from TXT file (one line per post). Mention IDs are added to every post.</div>',
            unsafe_allow_html=True
        )

        p1, p2 = st.columns(2)
        with p1:
            target_url = st.text_input(
                "Target URL (Profile / Group / Page)",
                placeholder="https://facebook.com/groups/... or profile ID",
                key="p_target"
            )
            prefix_p = st.text_input("Post Prefix (optional)", placeholder="e.g. 🔥 Check this out!", key="p_prefix")
            delay_p = st.number_input("Delay Between Posts (seconds)", 30, 7200, 120, key="p_delay")

        with p2:
            cookies_p = st.text_area("Cookies", height=120,
                                     placeholder="Paste your FB cookies here...", key="p_cookies")
            mention_input = st.text_area(
                "Mention IDs/UIDs/Links (one per line)",
                height=80,
                placeholder="123456789\nhttps://facebook.com/username\n@friendname",
                key="p_mention"
            )

        uploaded_txt = st.file_uploader(
            "Upload Post Text TXT (one line = one post)",
            type=['txt'],
            key="p_txt"
        )
        text_lines = []
        if uploaded_txt:
            raw = uploaded_txt.read().decode('utf-8')
            text_lines = [l.strip() for l in raw.split('\n') if l.strip()]
            st.success(f"Loaded {len(text_lines)} post lines from file")
        else:
            manual_text = st.text_area(
                "Post Text Lines (one per line = one post)",
                height=80,
                placeholder="First post text\nSecond post text\nThird post text",
                key="p_manual_text"
            )
            if manual_text.strip():
                text_lines = [l.strip() for l in manual_text.split('\n') if l.strip()]

        uploaded_images = st.file_uploader(
            "Upload Images (cycle order: img1→post1, img2→post2...)",
            type=['jpg', 'jpeg', 'png', 'gif', 'webp'],
            accept_multiple_files=True,
            key="p_images"
        )

        if uploaded_images:
            st.info(f"✅ {len(uploaded_images)} image(s) uploaded — will cycle through them")
            cols = st.columns(min(len(uploaded_images), 5))
            for i, img in enumerate(uploaded_images[:5]):
                with cols[i]:
                    st.image(img, width=80, caption=f"#{i+1}")
            if len(uploaded_images) > 5:
                st.caption(f"...and {len(uploaded_images) - 5} more")

        mention_ids = [m.strip() for m in mention_input.split('\n') if m.strip()] if mention_input else []

        st.markdown("**Preview of first post:**")
        preview_line = text_lines[0] if text_lines else "(no text)"
        preview_text = build_post_text(prefix_p, mention_ids, preview_line)
        st.code(preview_text[:200], language=None)

        if st.button("▶ START AUTO POST SESSION", use_container_width=True, key="start_post"):
            if not cookies_p:
                st.error("Cookies required!")
            elif not target_url:
                st.error("Target URL/ID required!")
            elif not text_lines:
                st.error("Add post text (TXT file or manual lines)!")
            else:
                new_s = manager.create_session('post')
                image_paths = []
                if uploaded_images:
                    image_paths = save_uploaded_images(uploaded_images, new_s.id)
                start_post_session(
                    new_s, target_url, cookies_p, text_lines,
                    prefix_p, mention_ids, image_paths, delay_p
                )
                st.success(f"Auto-post session started! ID: `{new_s.id}`")
                time.sleep(1)
                st.rerun()

st.markdown("---")
st.markdown("### Active Sessions")

active = manager.get_active_sessions()
if active:
    st.markdown('<div class="active-sessions">', unsafe_allow_html=True)
    for s in active:
        icon = '📸' if s.session_type == 'post' else '💬'
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
        with col1:
            st.code(f"{icon} {s.id} ({s.session_type})", language=None)
        with col2:
            label = "posts" if s.session_type == 'post' else "comments"
            st.write(f"{s.count} {label}")
        with col3:
            if st.button("View", key=f"view_{s.id}"):
                st.session_state.view_session = s.id
                st.rerun()
        with col4:
            if st.button("Stop", key=f"stop_{s.id}"):
                manager.stop_session(s.id)
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("No active sessions")

stopped = [s for s in all_sessions if not s.running]
if stopped:
    with st.expander(f"Stopped Sessions ({len(stopped)})"):
        for s in stopped[-10:]:
            icon = '📸' if s.session_type == 'post' else '💬'
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            with col1:
                st.code(f"{icon} {s.id}", language=None)
            with col2:
                st.write(f"{s.count} actions")
            with col3:
                if st.button("Logs", key=f"logs_{s.id}"):
                    st.session_state.view_session = s.id
                    st.rerun()
            with col4:
                if st.button("Delete", key=f"del_{s.id}"):
                    manager.delete_session(s.id)
                    st.rerun()

st.markdown("---")
lookup_id = st.text_input("🔍 Session ID Lookup:", placeholder="Enter session ID")
if lookup_id and st.button("Find Session"):
    if manager.get_session(lookup_id.upper()):
        st.session_state.view_session = lookup_id.upper()
        st.rerun()
    else:
        st.error("Session not found")
