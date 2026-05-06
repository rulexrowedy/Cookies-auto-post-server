import streamlit as st
import time
import threading
import gc
import json
import os
import uuid
import random
import subprocess
from pathlib import Path
from collections import deque
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

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
        0%  { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0,255,0,0.7); }
        70% { transform: scale(1);    box-shadow: 0 0 0 5px rgba(0,255,0,0); }
        100%{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0,255,0,0); }
    }
    [data-testid="stMetricValue"] { color: #4ecdc4; font-weight: 700; }
    .active-sessions { background: rgba(0,0,0,0.4); border: 1px solid rgba(78,205,196,0.5); border-radius: 10px; padding: 15px; margin-top: 20px; }
    .tab-header { color: white; font-size: 1.1rem; font-weight: 600; margin-bottom: 10px; }
    .info-box { background: rgba(78,205,196,0.15); border: 1px solid rgba(78,205,196,0.4); border-radius: 8px; padding: 10px; color: white; font-size: 12px; margin: 8px 0; }
</style>
"""

st.markdown(custom_css, unsafe_allow_html=True)
st.markdown(KEEP_ALIVE_JS, unsafe_allow_html=True)

SESSIONS_FILE  = "sessions_registry.json"
LOGS_DIR       = "session_logs"
TEMP_IMAGES_DIR= "temp_images"
MAX_LOGS       = 30

os.makedirs(LOGS_DIR,        exist_ok=True)
os.makedirs(TEMP_IMAGES_DIR, exist_ok=True)


# ─── Session ────────────────────────────────────────────────────────────────

class Session:
    __slots__ = ['id','running','count','logs','idx','img_idx',
                 'driver','start_time','profile_id','session_type']

    def __init__(self, sid, session_type='comment'):
        self.id           = sid
        self.running      = False
        self.count        = 0
        self.logs         = deque(maxlen=MAX_LOGS)
        self.idx          = 0
        self.img_idx      = 0
        self.driver       = None
        self.start_time   = None
        self.profile_id   = None
        self.session_type = session_type

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        pfx = f" {self.profile_id}" if self.profile_id else ""
        entry = f"[{ts}]{pfx} {msg}"
        self.logs.append(entry)
        try:
            with open(f"{LOGS_DIR}/{self.id}.log", "a") as f:
                f.write(entry + "\n")
        except:
            pass


@st.cache_resource
def get_session_manager():
    return SessionManager()


class SessionManager:
    def __init__(self):
        self.sessions = {}
        self.lock     = threading.Lock()
        self._load_registry()

    def _load_registry(self):
        if not os.path.exists(SESSIONS_FILE):
            return
        try:
            with open(SESSIONS_FILE, 'r') as f:
                data = json.load(f)
            for sid, info in data.items():
                if sid not in self.sessions:
                    s           = Session(sid, info.get('session_type','comment'))
                    s.count     = info.get('count', 0)
                    s.running   = False
                    s.start_time= info.get('start_time')
                    self.sessions[sid] = s
        except:
            pass

    def _save_registry(self):
        try:
            data = {sid: {'count': s.count, 'running': s.running,
                          'start_time': s.start_time, 'session_type': s.session_type}
                    for sid, s in self.sessions.items()}
            with open(SESSIONS_FILE, 'w') as f:
                json.dump(data, f)
        except:
            pass

    def create_session(self, session_type='comment'):
        with self.lock:
            sid = uuid.uuid4().hex[:8].upper()
            s   = Session(sid, session_type)
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
                try: s.driver.quit()
                except: pass
                s.driver = None
            self._save_registry()

    def delete_session(self, sid):
        with self.lock:
            s = self.sessions.get(sid)
            if s:
                s.running = False
                if s.driver:
                    try: s.driver.quit()
                    except: pass
                    s.driver = None
                del self.sessions[sid]
                try: os.remove(f"{LOGS_DIR}/{sid}.log")
                except: pass
                self._save_registry()
                gc.collect()

    def get_logs(self, sid, limit=30):
        log_file = f"{LOGS_DIR}/{sid}.log"
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    return f.readlines()[-limit:]
            except:
                pass
        s = self.sessions.get(sid)
        return list(s.logs)[-limit:] if s else []

    def update_count(self, sid, count):
        s = self.sessions.get(sid)
        if s:
            s.count = count
            self._save_registry()


manager = get_session_manager()


# ─── Browser helpers ─────────────────────────────────────────────────────────

def _find_chromedriver_path():
    """Return chromedriver binary path, trying multiple strategies."""
    import glob as _glob

    # 1. Known system paths
    for p in ['/usr/bin/chromedriver', '/usr/local/bin/chromedriver',
              '/usr/lib/chromium/chromedriver', '/usr/lib/chromium-browser/chromedriver']:
        if Path(p).exists() and os.access(p, os.X_OK):
            return p

    # 2. which command
    for cmd in ['chromedriver', 'chromium.chromedriver']:
        try:
            r = subprocess.run(['which', cmd], capture_output=True, text=True, timeout=5)
            p = r.stdout.strip()
            if p and Path(p).exists():
                return p
        except:
            pass

    # 3. Glob search in common cache dirs (selenium-manager puts it here)
    patterns = [
        '/home/**/.cache/selenium/chromedriver/**/chromedriver',
        '/root/.cache/selenium/chromedriver/**/chromedriver',
        '/home/appuser/.cache/selenium/**/chromedriver',
        '/tmp/.cache/selenium/**/chromedriver',
        os.path.expanduser('~/.cache/selenium/**/chromedriver'),
    ]
    for pat in patterns:
        try:
            found = [f for f in _glob.glob(pat, recursive=True)
                     if os.path.isfile(f)]
            if found:
                drv = found[0]
                try: os.chmod(drv, 0o755)
                except: pass
                return drv
        except:
            pass

    # 4. webdriver-manager (downloads correct version)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        drv = ChromeDriverManager().install()
        if drv and os.path.isfile(drv):
            try: os.chmod(drv, 0o755)
            except: pass
            return drv
    except:
        pass

    return None


def _find_chromium_path():
    """Return chromium binary path."""
    for p in ['/usr/bin/chromium', '/usr/bin/chromium-browser',
              '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable']:
        if Path(p).exists():
            return p
    try:
        r = subprocess.run(['which', 'chromium', 'chromium-browser', 'google-chrome'],
                           capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            return r.stdout.strip().split('\n')[0]
    except:
        pass
    return None


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
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
    )

    chrome_bin = _find_chromium_path()
    if chrome_bin:
        opts.binary_location = chrome_bin
        session.log(f'Chromium: {chrome_bin}')

    drv_path = _find_chromedriver_path()
    if drv_path:
        session.log(f'Chromedriver: {drv_path}')
        try: os.chmod(drv_path, 0o755)
        except: pass
        svc    = Service(executable_path=drv_path)
        driver = webdriver.Chrome(service=svc, options=opts)
    else:
        session.log('No chromedriver found, trying auto-detect...')
        driver = webdriver.Chrome(options=opts)

    driver.set_window_size(1920, 1080)
    try:
        driver.execute_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    except:
        pass
    session.log('Browser ready!')
    return driver


def login_with_cookies(driver, cookies, session):
    session.log('Navigating to Facebook...')
    driver.get('https://www.facebook.com/')
    time.sleep(8)
    session.log('Adding cookies...')
    for c in cookies.split(';'):
        c = c.strip()
        if c and '=' in c:
            i = c.find('=')
            try:
                driver.add_cookie({
                    'name'  : c[:i].strip(),
                    'value' : c[i+1:].strip(),
                    'domain': '.facebook.com',
                    'path'  : '/'
                })
            except:
                pass
    driver.refresh()
    time.sleep(8)
    session.log('Login complete.')


def extract_fb_uid(cookies):
    try:
        for c in cookies.split(';'):
            c = c.strip()
            if '=' in c:
                k, v = c.split('=', 1)
                k = k.strip()
                if k in ('c_user', 'uid'):
                    return v.strip()
    except:
        pass
    return "Unknown"


def fetch_fb_name(driver, uid):
    """Visit profile page and scrape the display name."""
    try:
        driver.get(f'https://www.facebook.com/{uid}')
        time.sleep(8)
        name = driver.execute_script("""
            try {
                let h1 = document.querySelector('h1');
                if (h1 && h1.textContent.trim().length > 1)
                    return h1.textContent.trim();
                let spans = document.querySelectorAll('h1 span');
                for (let s of spans) {
                    if (s.textContent.trim().length > 1)
                        return s.textContent.trim();
                }
                return null;
            } catch(e) { return null; }
        """)
        return name.strip() if name else uid
    except:
        return uid


def simulate_human(driver):
    try:
        driver.execute_script("""
            window.scrollBy(0, Math.random()*200-100);
            document.dispatchEvent(new MouseEvent('mousemove',{
                bubbles:true,
                clientX:Math.random()*window.innerWidth,
                clientY:Math.random()*window.innerHeight
            }));
        """)
    except:
        pass


# ─── Comment helpers ──────────────────────────────────────────────────────────

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
        '[contenteditable="true"]',
    ]
    for idx, sel in enumerate(selectors):
        try:
            for elem in driver.find_elements(By.CSS_SELECTOR, sel):
                try:
                    ok = driver.execute_script(
                        "return arguments[0].contentEditable==='true' || "
                        "arguments[0].tagName==='TEXTAREA' || "
                        "arguments[0].tagName==='INPUT';", elem)
                    if ok:
                        try: elem.click(); time.sleep(0.5)
                        except: pass
                        session.log(f'Comment input found (selector #{idx+1})')
                        return elem
                except:
                    continue
        except:
            continue
    return None


def type_text(driver, elem, text):
    driver.execute_script("""
        var el = arguments[0], msg = arguments[1];
        el.scrollIntoView({behavior:'smooth', block:'center'});
        el.focus(); el.click();
        if (el.tagName === 'DIV') {
            el.textContent = msg;
            el.innerHTML   = msg;
        } else {
            el.value = msg;
        }
        el.dispatchEvent(new Event('input',  {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
        el.dispatchEvent(new InputEvent('input', {bubbles:true, data:msg}));
    """, elem, text)


def press_enter(driver, elem):
    driver.execute_script("""
        var el = arguments[0]; el.focus();
        ['keydown','keypress','keyup'].forEach(function(t){
            el.dispatchEvent(new KeyboardEvent(t,
                {key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
        });
    """, elem)


# ─── Post helpers (new — mirrors comment approach) ────────────────────────────


def save_uploaded_images(uploaded_files, session_id):
    d = os.path.join(TEMP_IMAGES_DIR, session_id)
    os.makedirs(d, exist_ok=True)
    paths = []
    for i, f in enumerate(uploaded_files):
        ext  = Path(f.name).suffix or '.jpg'
        path = os.path.abspath(os.path.join(d, f"{i:03d}{ext}"))
        with open(path, 'wb') as fp:
            fp.write(f.read())
        paths.append(path)
    return paths


# ─── Session runners ──────────────────────────────────────────────────────────

def run_comment_session(session, post_id, cookies, comments_list, prefix, delay):
    retries = 0
    driver  = None
    fb_uid  = extract_fb_uid(cookies)

    while session.running and retries < 10:
        try:
            if driver is None:
                driver         = setup_browser(session)
                session.driver = driver
            login_with_cookies(driver, cookies, session)

            profile_name       = fetch_fb_name(driver, fb_uid)
            session.profile_id = f"📌{profile_name}"
            session.log(f'Profile: {profile_name}')

            session.log('Opening post...')
            url = post_id if post_id.startswith('http') else f'https://www.facebook.com/{post_id}'
            driver.get(url)
            time.sleep(15)
            session.log('ID Online - Browser Active!')

            not_found = 0
            while session.running:
                try:
                    inp = find_comment_input(driver, session)
                    if not inp:
                        not_found += 1
                        if not_found >= 3:
                            session.log('Comment input not found 3x — stopping.')
                            session.running = False
                            break
                        session.log(f'Not found ({not_found}/3), refreshing...')
                        driver.get(driver.current_url)
                        time.sleep(15)
                        continue

                    not_found = 0
                    base   = comments_list[session.idx % len(comments_list)]
                    session.idx += 1
                    text   = f"{prefix} {base}" if prefix else base
                    session.log(f'Typing: {text[:40]}...')

                    type_text(driver, inp, text)
                    time.sleep(1)
                    press_enter(driver, inp)
                    time.sleep(1)

                    session.count += 1
                    manager.update_count(session.id, session.count)
                    session.log(f'✅ Comment #{session.count} sent!')
                    retries = 0

                    wait = max(10, int(delay + random.uniform(-10, 10)))
                    session.log(f'Waiting {wait}s...')
                    for i in range(wait):
                        if not session.running: break
                        if i and i % 15 == 0: simulate_human(driver)
                        time.sleep(1)

                    if session.count % 2 == 0:
                        gc.collect()
                        try: driver.execute_script(
                            "window.localStorage.clear();window.sessionStorage.clear();")
                        except: pass

                except Exception as e:
                    err = str(e)[:60]
                    session.log(f'Error: {err}')
                    if 'session' in err.lower() or 'disconnect' in err.lower():
                        try: driver.quit()
                        except: pass
                        driver  = None
                        retries += 1
                        time.sleep(5)
                        break
                    time.sleep(10)

        except Exception as e:
            session.log(f'Fatal: {str(e)[:60]}')
            retries += 1
            try: driver.quit()
            except: pass
            driver = None
            time.sleep(10)

    session.running = False
    session.log('Stopped.')
    manager._save_registry()
    if driver:
        try: driver.quit()
        except: pass
    gc.collect()


def _find_post_composer_textbox(driver, session):
    """
    Navigate to home feed, click 'What's on your mind?', return the
    contenteditable textbox — same pattern as find_comment_input.
    """
    session.log('Going to home feed...')
    driver.get('https://www.facebook.com/')
    time.sleep(12)

    # Scroll a little so the composer is in view
    try:
        driver.execute_script("window.scrollTo(0, 300);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
    except:
        pass

    # Click the "What's on your mind?" placeholder
    session.log('Clicking post composer button...')
    clicked = driver.execute_script("""
        var all = document.querySelectorAll('[role="button"]');
        for (var i = 0; i < all.length; i++) {
            var t = (all[i].textContent || all[i].getAttribute('aria-label') || '').toLowerCase();
            if ((t.includes('what') && t.includes('mind')) ||
                 t.includes('write something') || t.includes('create post')) {
                all[i].click(); return true;
            }
        }
        return false;
    """)

    if not clicked:
        # Try direct aria-label selectors
        for sel in [
            'div[aria-label*="mind" i]',
            'div[aria-label*="Write something" i]',
            'div[aria-label*="Create post" i]',
            'div[aria-label*="on your mind" i]',
        ]:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    elems[0].click()
                    clicked = True
                    break
            except:
                pass

    if clicked:
        session.log('Composer button clicked, waiting for dialog...')
        time.sleep(5)
    else:
        session.log('Composer button not found by click — trying direct textbox search')

    # Find the contenteditable textbox (same selectors as comment input)
    selectors = [
        'div[role="dialog"] div[contenteditable="true"][role="textbox"]',
        'div[role="dialog"] div[contenteditable="true"]',
        'div[contenteditable="true"][role="textbox"]',
        'div[data-lexical-editor="true"]',
        'div[contenteditable="true"][spellcheck="true"]',
        '[role="textbox"][contenteditable="true"]',
        'div[contenteditable="true"]',
    ]
    for idx, sel in enumerate(selectors):
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            for elem in elems:
                try:
                    ok = driver.execute_script(
                        "return arguments[0].contentEditable === 'true';", elem)
                    if ok:
                        try: elem.click(); time.sleep(0.5)
                        except: pass
                        session.log(f'Composer textbox found (selector #{idx+1})')
                        return elem
                except:
                    continue
        except:
            continue
    return None


def _attach_image(driver, session, img_abs_path):
    """Attach an image to the open composer — make file inputs visible then send path."""
    session.log(f'Attaching image: {Path(img_abs_path).name}')
    try:
        # Reveal any hidden file inputs
        driver.execute_script("""
            document.querySelectorAll('input[type="file"]').forEach(function(el){
                el.style.display    = 'block';
                el.style.visibility = 'visible';
                el.style.opacity    = '1';
                el.style.position   = 'fixed';
                el.style.top        = '0';
                el.style.left       = '0';
            });
        """)
        time.sleep(1)
        inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        if inputs:
            inputs[0].send_keys(img_abs_path)
            time.sleep(6)
            session.log('Image attached!')
            return True
        # Try clicking Photo/Video button first to reveal the input
        for sel in ['div[aria-label*="Photo" i]', 'div[aria-label*="photo" i]',
                    'div[aria-label*="Add photo" i]']:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
            if btns:
                try:
                    btns[0].click()
                    time.sleep(3)
                    inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
                    if inputs:
                        inputs[0].send_keys(img_abs_path)
                        time.sleep(6)
                        session.log('Image attached via photo button!')
                        return True
                except:
                    pass
        session.log('File input not found — posting without image.')
        return False
    except Exception as e:
        session.log(f'Image error: {str(e)[:50]}')
        return False


def _click_post_button(driver, session):
    """Click the final Post/Share/Publish button."""
    session.log('Clicking POST button...')
    clicked = driver.execute_script("""
        var all = document.querySelectorAll('[role="button"]');
        for (var i = 0; i < all.length; i++) {
            var t = (all[i].textContent || all[i].getAttribute('aria-label') || '').trim().toLowerCase();
            if (t === 'post' || t === 'share now' || t === 'publish' || t === 'share') {
                all[i].click(); return true;
            }
        }
        return false;
    """)
    if clicked:
        time.sleep(5)
        session.log('Post button clicked!')
        return True
    for sel in ['div[aria-label="Post"][role="button"]', 'button[type="submit"]']:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                elems[0].click()
                time.sleep(5)
                session.log('Post submitted (fallback)!')
                return True
        except:
            pass
    session.log('POST button not found!')
    return False


def run_post_session(session, cookies, text_lines, prefix,
                     mention_names, image_paths, delay):
    """
    Auto-post on user's own profile.
    Same structure as run_comment_session:
      setup_browser → login_with_cookies → find composer → type → attach image → submit
    """
    retries = 0
    driver  = None
    fb_uid  = extract_fb_uid(cookies)

    while session.running and retries < 10:
        try:
            if driver is None:
                driver         = setup_browser(session)
                session.driver = driver

            login_with_cookies(driver, cookies, session)

            own_name           = fetch_fb_name(driver, fb_uid)
            session.profile_id = f"📌{own_name}"
            session.log(f'Logged in as: {own_name} (UID: {fb_uid})')
            session.log('ID Online - Browser Active!')

            fail_count = 0
            while session.running:
                try:
                    # Build post text
                    line = text_lines[session.idx % len(text_lines)] if text_lines else ''
                    session.idx += 1
                    parts = []
                    if prefix.strip():          parts.append(prefix.strip())
                    if mention_names:           parts.append(' '.join(mention_names))
                    if line.strip():            parts.append(line.strip())
                    post_text = ' '.join(parts)

                    session.log(f'Post #{session.count+1}: {post_text[:50]}...')

                    # Find the composer textbox (same approach as comment input)
                    textbox = _find_post_composer_textbox(driver, session)

                    if not textbox:
                        fail_count += 1
                        session.log(f'Composer not found ({fail_count}/3), refreshing...')
                        if fail_count >= 3:
                            session.log('3 failures — restarting browser...')
                            try: driver.quit()
                            except: pass
                            driver  = None
                            retries += 1
                            time.sleep(10)
                            break
                        driver.get(driver.current_url)
                        time.sleep(15)
                        continue

                    fail_count = 0

                    # Type text — same JS method as comment
                    session.log(f'Typing: {post_text[:40]}...')
                    type_text(driver, textbox, post_text)
                    time.sleep(2)

                    # Attach image (cycle)
                    if image_paths:
                        img = image_paths[session.img_idx % len(image_paths)]
                        session.img_idx += 1
                        session.log(f'Image {session.img_idx}/{len(image_paths)}: {Path(img).name}')
                        _attach_image(driver, session, img)
                        time.sleep(2)

                    # Submit post
                    ok = _click_post_button(driver, session)
                    if ok:
                        session.count += 1
                        manager.update_count(session.id, session.count)
                        session.log(f'✅ Post #{session.count} done!')
                        retries = 0
                    else:
                        session.log('Submit failed, closing composer...')
                        try:
                            driver.execute_script(
                                "var c=document.querySelector('[aria-label=\"Close\"]');"
                                "if(c)c.click();")
                        except: pass
                        time.sleep(5)

                    session.log(f'Waiting {delay}s...')
                    for i in range(int(delay)):
                        if not session.running: break
                        if i and i % 20 == 0: simulate_human(driver)
                        time.sleep(1)

                    if session.count % 3 == 0:
                        gc.collect()

                except Exception as e:
                    err = str(e)[:60]
                    session.log(f'Error: {err}')
                    if 'session' in err.lower() or 'disconnect' in err.lower():
                        try: driver.quit()
                        except: pass
                        driver  = None
                        retries += 1
                        time.sleep(10)
                        break
                    time.sleep(10)

        except Exception as e:
            session.log(f'Fatal: {str(e)[:60]}')
            retries += 1
            try: driver.quit()
            except: pass
            driver = None
            time.sleep(10)

    session.running = False
    session.log('Stopped.')
    manager._save_registry()
    if driver:
        try: driver.quit()
        except: pass
    gc.collect()


# ─── Session starters ─────────────────────────────────────────────────────────

def start_comment_session(session, post_id, cookies, comments, prefix, delay):
    session.running    = True
    session.logs       = deque(maxlen=MAX_LOGS)
    session.count      = 0
    session.idx        = 0
    session.start_time = time.strftime("%H:%M:%S")
    try: open(f"{LOGS_DIR}/{session.id}.log", 'w').close()
    except: pass
    session.log(f'Session {session.id} — comment mode')
    manager._save_registry()
    lines = [c.strip() for c in comments.split('\n') if c.strip()] or ['Nice post!']
    threading.Thread(
        target=run_comment_session,
        args=(session, post_id, cookies, lines, prefix, delay),
        daemon=True
    ).start()


def start_post_session(session, cookies, text_lines, prefix,
                       mention_ids_raw, image_paths, delay):
    session.running    = True
    session.logs       = deque(maxlen=MAX_LOGS)
    session.count      = 0
    session.idx        = 0
    session.img_idx    = 0
    session.start_time = time.strftime("%H:%M:%S")
    try: open(f"{LOGS_DIR}/{session.id}.log", 'w').close()
    except: pass
    session.log(f'Session {session.id} — auto-post mode')
    manager._save_registry()

    # Pre-format mention strings as @name or link
    mention_names = []
    for m in mention_ids_raw:
        m = m.strip()
        if not m:
            continue
        if m.startswith('http'):
            mention_names.append(m)
        elif m.lstrip('@').isdigit():
            mention_names.append(f'@{m.lstrip("@")}')
        else:
            mention_names.append(f'@{m.lstrip("@")}')

    threading.Thread(
        target=run_post_session,
        args=(session, cookies, text_lines, prefix,
              mention_names, image_paths, delay),
        daemon=True
    ).start()


# ─── UI ───────────────────────────────────────────────────────────────────────

st.markdown('<div class="main-header"><h1>🚀 FB Auto Tool</h1></div>', unsafe_allow_html=True)

all_sessions    = manager.get_all_sessions()
active_sessions = manager.get_active_sessions()
total_actions   = sum(s.count for s in all_sessions)

c1, c2, c3 = st.columns(3)
c1.metric("Total Actions",   total_actions)
c2.metric("Active Sessions", len(active_sessions))
c3.metric("All Sessions",    len(all_sessions))

if 'view_session' not in st.session_state:
    st.session_state.view_session = None

st.markdown("---")

# ── Session detail view ──────────────────────────────────────────────────────
if st.session_state.view_session:
    sid     = st.session_state.view_session
    session = manager.get_session(sid)
    stype   = session.session_type if session else 'comment'
    icon    = '📸' if stype == 'post' else '💬'

    st.markdown(f"### {icon} Session: `{sid}` — **{stype.upper()}**")

    if session:
        label = "posts" if stype == 'post' else "comments"
        if session.running:
            pid = f" — {session.profile_id}" if session.profile_id else ""
            st.markdown(
                f'<div class="status-running"><span class="online-indicator"></span>'
                f'RUNNING — {session.count} {label}{pid}</div>',
                unsafe_allow_html=True)
        else:
            st.markdown('<div class="status-stopped">STOPPED</div>', unsafe_allow_html=True)

        logs = manager.get_logs(sid, 25)
        html = '<div class="console-box">' + \
               ''.join(f'<div class="log-line">{l.strip()}</div>' for l in logs) + \
               '</div>'
        st.markdown(html if logs else '<div class="console-box">No logs yet...</div>',
                    unsafe_allow_html=True)

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("STOP Session", disabled=not session.running):
                manager.stop_session(sid); st.rerun()
        with b2:
            if st.button("Delete Session"):
                manager.delete_session(sid)
                st.session_state.view_session = None; st.rerun()
        with b3:
            if st.button("Refresh Logs"): st.rerun()
        with b4:
            if st.button("Back"):
                st.session_state.view_session = None; st.rerun()
    else:
        st.error("Session not found")
        if st.button("Back"):
            st.session_state.view_session = None; st.rerun()

else:
    # ── Main tabs ────────────────────────────────────────────────────────────
    tab1, tab2 = st.tabs(["💬 Auto Comment", "📸 Auto Post"])

    # ── Tab 1: Auto Comment ──────────────────────────────────────────────────
    with tab1:
        st.markdown('<div class="tab-header">Auto Comment on a Post</div>', unsafe_allow_html=True)
        ct1, ct2 = st.columns(2)
        with ct1:
            post_id  = st.text_input("Post ID / URL",
                                     placeholder="https://facebook.com/... or post ID",
                                     key="c_post")
            prefix_c = st.text_input("Prefix (optional)",
                                     placeholder="e.g. 🔥  or @tag",
                                     key="c_prefix")
            delay_c  = st.number_input("Delay (seconds)", 10, 3600, 30, key="c_delay")
        with ct2:
            cookies_c = st.text_area("Cookies", height=130,
                                     placeholder="Paste your FB cookies here...",
                                     key="c_cookies")

        up_c = st.file_uploader("Upload Comments TXT (one per line)", type=['txt'], key="c_txt")
        if up_c:
            comments = up_c.read().decode('utf-8')
            st.success(f"Loaded {len([l for l in comments.splitlines() if l.strip()])} comments")
        else:
            comments = st.text_area("Comments (one per line)", height=80,
                                    placeholder="Nice!\nGreat post!\nLove this!",
                                    key="c_manual")

        if st.button("▶ START COMMENT SESSION", use_container_width=True, key="btn_comment"):
            if not cookies_c.strip():
                st.error("Cookies required!")
            elif not post_id.strip():
                st.error("Post ID / URL required!")
            elif not comments.strip():
                st.error("Add at least one comment!")
            else:
                ns = manager.create_session('comment')
                start_comment_session(ns, post_id, cookies_c, comments, prefix_c, delay_c)
                st.success(f"Session started! ID: `{ns.id}`")
                time.sleep(1); st.rerun()

    # ── Tab 2: Auto Post ─────────────────────────────────────────────────────
    with tab2:
        st.markdown('<div class="tab-header">Auto Post on Your Own Profile</div>',
                    unsafe_allow_html=True)
        st.markdown(
            '<div class="info-box">'
            '📌 Posts go to <b>your own profile</b> (from the cookie\'s c_user ID). '
            'Images cycle one-by-one per post. Text comes from TXT file (1 line = 1 post). '
            'Mention IDs/UIDs are added as @mentions in every post.'
            '</div>', unsafe_allow_html=True)

        pt1, pt2 = st.columns(2)
        with pt1:
            prefix_p = st.text_input("Post Prefix (optional)",
                                     placeholder="e.g. 🔥 Check this out!",
                                     key="p_prefix")
            delay_p  = st.number_input("Delay Between Posts (seconds)",
                                       30, 7200, 120, key="p_delay")
        with pt2:
            cookies_p = st.text_area("Cookies", height=130,
                                     placeholder="Paste your FB cookies here...",
                                     key="p_cookies")

        mention_raw = st.text_area(
            "Mention IDs / UIDs / @names (one per line) — added to every post",
            height=80,
            placeholder="123456789\n@friend.name\nhttps://facebook.com/username",
            key="p_mention"
        )

        up_p = st.file_uploader(
            "Upload Post Text TXT (one line = one post)", type=['txt'], key="p_txt")
        text_lines = []
        if up_p:
            raw = up_p.read().decode('utf-8')
            text_lines = [l.strip() for l in raw.splitlines() if l.strip()]
            st.success(f"Loaded {len(text_lines)} post lines")
        else:
            manual = st.text_area("Post Text Lines (one line = one post)", height=80,
                                  placeholder="First post\nSecond post\nThird post",
                                  key="p_manual")
            if manual.strip():
                text_lines = [l.strip() for l in manual.splitlines() if l.strip()]

        up_imgs = st.file_uploader(
            "Upload Images — cycle per post (img1→post1, img2→post2 ...)",
            type=['jpg','jpeg','png','gif','webp'],
            accept_multiple_files=True,
            key="p_imgs"
        )
        if up_imgs:
            st.info(f"✅ {len(up_imgs)} image(s) loaded")
            cols = st.columns(min(len(up_imgs), 5))
            for i, img in enumerate(up_imgs[:5]):
                with cols[i]:
                    st.image(img, width=75, caption=f"#{i+1}")
            if len(up_imgs) > 5:
                st.caption(f"...and {len(up_imgs)-5} more")

        # Live preview
        mention_ids_raw = [m.strip() for m in mention_raw.splitlines() if m.strip()]
        preview_line    = text_lines[0] if text_lines else "(no text yet)"
        preview_parts   = []
        if prefix_p.strip():     preview_parts.append(prefix_p.strip())
        for m in mention_ids_raw:
            m = m.strip()
            if m.startswith('http'): preview_parts.append(m)
            else:                    preview_parts.append(f'@{m.lstrip("@")}')
        if preview_line:              preview_parts.append(preview_line)
        st.markdown("**Preview of first post:**")
        st.code(' '.join(preview_parts)[:250], language=None)

        if st.button("▶ START AUTO POST SESSION", use_container_width=True, key="btn_post"):
            if not cookies_p.strip():
                st.error("Cookies required!")
            elif not text_lines:
                st.error("Add post text (TXT file or manual lines)!")
            else:
                ns = manager.create_session('post')
                img_paths = []
                if up_imgs:
                    img_paths = save_uploaded_images(up_imgs, ns.id)
                start_post_session(ns, cookies_p, text_lines, prefix_p,
                                   mention_ids_raw, img_paths, delay_p)
                st.success(f"Auto-post session started! ID: `{ns.id}`")
                time.sleep(1); st.rerun()

# ── Active sessions ───────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Active Sessions")

active = manager.get_active_sessions()
if active:
    st.markdown('<div class="active-sessions">', unsafe_allow_html=True)
    for s in active:
        icon  = '📸' if s.session_type == 'post' else '💬'
        label = 'posts' if s.session_type == 'post' else 'comments'
        c1, c2, c3, c4 = st.columns([2,1,1,1])
        with c1: st.code(f"{icon} {s.id} ({s.session_type})", language=None)
        with c2: st.write(f"{s.count} {label}")
        with c3:
            if st.button("View", key=f"view_{s.id}"):
                st.session_state.view_session = s.id; st.rerun()
        with c4:
            if st.button("Stop", key=f"stop_{s.id}"):
                manager.stop_session(s.id); st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.info("No active sessions")

stopped = [s for s in all_sessions if not s.running]
if stopped:
    with st.expander(f"Stopped Sessions ({len(stopped)})"):
        for s in stopped[-10:]:
            icon = '📸' if s.session_type == 'post' else '💬'
            c1, c2, c3, c4 = st.columns([2,1,1,1])
            with c1: st.code(f"{icon} {s.id}", language=None)
            with c2: st.write(f"{s.count} actions")
            with c3:
                if st.button("Logs",   key=f"logs_{s.id}"):
                    st.session_state.view_session = s.id; st.rerun()
            with c4:
                if st.button("Delete", key=f"del_{s.id}"):
                    manager.delete_session(s.id); st.rerun()

st.markdown("---")
lookup = st.text_input("🔍 Session ID Lookup:", placeholder="Enter session ID")
if lookup and st.button("Find Session"):
    if manager.get_session(lookup.upper()):
        st.session_state.view_session = lookup.upper(); st.rerun()
    else:
        st.error("Session not found")
