#!/usr/bin/env python3
"""
rw-ticket.py — скачивает все билеты с pass.rw.by через мобильный API.

Использование:
  python rw-ticket.py

Первый запуск: открывает браузер с формой логина.
Последующие запуски: использует сохранённый JWT (живёт 10 дней).
"""

import base64
import http.server
import json
import threading
import time
import urllib.parse
import subprocess
import webbrowser
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    import sys
    print("Установи зависимости: pip install requests PyPDF2")
    sys.exit(1)

# ── Константы ─────────────────────────────────────────────────────────────────
API_URL = "https://apicast.rw.by"
USER_KEY = "c0f1de1cbcf6c517baa7c95ab7d0509e"
ORDER_TYPES = ["UPCOMING"]

CONF_FILE = Path.home() / ".rw-ticket.conf"
DOWNLOAD_DIR = Path("/sdcard/Download")
if not DOWNLOAD_DIR.exists():
    DOWNLOAD_DIR = Path.home() / "Downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

PORT = 8765

# ── Глобальное состояние ──────────────────────────────────────────────────────
_state = {"status": "idle", "log": [], "done": False, "error": None, "result_file": None}
_server = None


# ── Конфиг ────────────────────────────────────────────────────────────────────
def _load_conf():
    if not CONF_FILE.exists():
        return {}
    data = {}
    for line in CONF_FILE.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def _save_conf(data):
    CONF_FILE.write_text("\n".join(f"{k}={v}" for k, v in data.items()) + "\n")
    CONF_FILE.chmod(0o600)


def load_credentials():
    d = _load_conf()
    return d.get("login"), d.get("password")


def save_credentials(login, password):
    d = _load_conf()
    d["login"] = login
    d["password"] = password
    _save_conf(d)


def load_jwt():
    d = _load_conf()
    return d.get("jwt")


def save_jwt(jwt):
    d = _load_conf()
    d["jwt"] = jwt
    _save_conf(d)


# ── JWT helpers ───────────────────────────────────────────────────────────────
def _jwt_exp(token):
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        return payload.get("exp", 0)
    except Exception:
        return 0


def _jwt_valid(token):
    return token and _jwt_exp(token) > time.time() + 60


# ── API ───────────────────────────────────────────────────────────────────────
def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "okhttp/4.9.0",
        "Accept": "application/json",
    })
    return s


def api_login(login, password):
    log("Авторизуюсь через мобильный API...")
    s = make_session()
    r = s.post(f"{API_URL}/v1/rwauth", data={
        "login": login,
        "password": password,
        "user_key": USER_KEY,
        "device_token": "",
        "refresh_token": "false",
    }, timeout=60)

    if r.status_code != 200:
        raise ValueError(f"Ошибка авторизации: {r.status_code}")

    data = r.json()
    if "auth" not in data or "jwt" not in data["auth"]:
        raise ValueError("Неверный логин или пароль")

    jwt = data["auth"]["jwt"]
    log("Авторизация успешна")
    save_jwt(jwt)
    return jwt


def get_jwt(login, password):
    cached = load_jwt()
    if _jwt_valid(cached):
        log("Использую сохранённый токен...")
        return cached
    return api_login(login, password)


def fetch_orders(session, order_type):
    r = session.get(
        f"{API_URL}/v1/unnumbered/orders",
        params={"user_key": USER_KEY, "orderType": order_type},
        timeout=60,
    )
    if r.status_code == 200:
        return r.json()
    return []


# ── Скачивание и merge ────────────────────────────────────────────────────────
def merge_pdfs(pdf_paths, output_path):
    try:
        from PyPDF2 import PdfMerger
        merger = PdfMerger()
        for p in pdf_paths:
            merger.append(str(p))
        merger.write(str(output_path))
        merger.close()
        return True
    except ImportError:
        if len(pdf_paths) == 1:
            pdf_paths[0].rename(output_path)
            return True
        return False
    except Exception as e:
        log(f"Ошибка объединения PDF: {e}")
        return False


def download_tickets(login, password):
    try:
        jwt = get_jwt(login, password)
        session = make_session()
        session.headers.update({"Authorization": f"Bearer {jwt}"})

        all_orders = []
        for order_type in ORDER_TYPES:
            log(f"Ищу заказы ({order_type})...")
            orders = fetch_orders(session, order_type)
            log(f"  → {len(orders)} заказов")
            all_orders.extend(orders)

        if not all_orders:
            log("Заказы не найдены.")
            _state["done"] = True
            return

        log(f"Всего заказов: {len(all_orders)}")

        all_pdfs = []
        for i, order in enumerate(all_orders):
            order_id = order["id"]
            ticket_id = order["ticketId"]
            ets = order.get("etsNum", "")
            log(f"Заказ {i+1}/{len(all_orders)} (№{ets})...")

            pdf_url = (
                f"{API_URL}/v1/unnumbered/orders/{order_id}/tickets/{ticket_id}.pdf"
                f"?user_key={USER_KEY}"
            )
            try:
                r = session.get(pdf_url, timeout=60)
                r.raise_for_status()
                tmp = DOWNLOAD_DIR / f"_rw_tmp_{i}.pdf"
                tmp.write_bytes(r.content)
                all_pdfs.append(tmp)
                log(f"  → OK ({len(r.content) // 1024} KB)")
            except Exception as e:
                log(f"  → Ошибка: {e}")

        if not all_pdfs:
            log("Билеты не найдены.")
            _state["done"] = True
            return

        result_path = DOWNLOAD_DIR / f"tickets_{date.today().isoformat()}.pdf"
        merged = merge_pdfs(all_pdfs, result_path)

        for p in all_pdfs:
            try:
                p.unlink()
            except Exception:
                pass

        if merged:
            log(f"Готово! Файл: {result_path}")
            _state["result_file"] = str(result_path)
        else:
            log(f"Сохранено {len(all_pdfs)} файлов в {DOWNLOAD_DIR}")

        _state["done"] = True

    except ValueError as e:
        log(f"Ошибка: {e}")
        _state["done"] = True
        _state["error"] = str(e)
    except Exception as e:
        log(f"Неожиданная ошибка: {e}")
        _state["done"] = True
        _state["error"] = str(e)


# ── Логирование ───────────────────────────────────────────────────────────────
def log(msg):
    print(msg)
    _state["log"].append(msg)
    _state["status"] = msg


# ── HTML ──────────────────────────────────────────────────────────────────────
LOGIN_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Скачать билеты БЧ</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#f0f4ff;min-height:100vh;display:flex;align-items:center;
  justify-content:center;padding:16px}
.card{background:#fff;border-radius:16px;padding:28px 24px;width:100%;
  max-width:380px;box-shadow:0 2px 16px rgba(0,61,153,.12)}
h1{font-size:1.3rem;font-weight:700;color:#003d99;margin-bottom:6px}
.sub{color:#6b7280;font-size:.88rem;margin-bottom:24px}
label{display:block;font-size:.88rem;font-weight:600;color:#374151;margin-bottom:5px}
input{width:100%;padding:12px 14px;border:1.5px solid #c7d7f5;border-radius:10px;
  font-size:1rem;margin-bottom:16px;outline:none}
input:focus{border-color:#003d99}
.btn{width:100%;padding:14px;background:#003d99;color:#fff;border:none;
  border-radius:10px;font-size:1rem;font-weight:700;cursor:pointer;margin-top:4px}
.btn:active{background:#002e80}
.note{font-size:.8rem;color:#9ca3af;margin-top:14px;text-align:center}
</style>
</head>
<body>
<div class="card">
  <h1>Скачать билеты БЧ</h1>
  <p class="sub">Войди в аккаунт pass.rw.by</p>
  <form method="POST" action="/login">
    <label>Логин (email)</label>
    <input type="email" name="login" autocomplete="email" required placeholder="example@mail.com">
    <label>Пароль</label>
    <input type="password" name="password" autocomplete="current-password" required>
    <button class="btn" type="submit">Скачать билеты</button>
  </form>
  <p class="note">Данные сохраняются только на устройстве</p>
</div>
</body>
</html>"""

PROGRESS_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Скачивание...</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#f0f4ff;min-height:100vh;display:flex;align-items:center;
  justify-content:center;padding:16px}
.card{background:#fff;border-radius:16px;padding:28px 24px;width:100%;
  max-width:380px;box-shadow:0 2px 16px rgba(0,61,153,.12)}
h1{font-size:1.3rem;font-weight:700;color:#003d99;margin-bottom:20px}
.log{background:#f8faff;border:1px solid #e5eaf5;border-radius:8px;
  padding:12px;font-size:.85rem;line-height:1.6;min-height:80px;
  max-height:300px;overflow-y:auto;color:#374151;white-space:pre-wrap}
.spinner{display:inline-block;width:16px;height:16px;border:2px solid #c7d7f5;
  border-top-color:#003d99;border-radius:50%;animation:spin .8s linear infinite;
  margin-right:8px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
.status{display:flex;align-items:center;margin-bottom:12px;font-size:.9rem;color:#6b7280}
.reset{display:block;margin-top:16px;text-align:center;font-size:.82rem;color:#9ca3af;
  text-decoration:none}
</style>
</head>
<body>
<div class="card">
  <h1>Скачивание билетов</h1>
  <div class="status"><span class="spinner" id="spin"></span><span id="status">Запуск...</span></div>
  <div class="log" id="log"></div>
  <a class="reset" href="/reset">Сменить аккаунт</a>
</div>
<script>
function poll(){
  fetch('/status').then(r=>r.json()).then(d=>{
    document.getElementById('status').textContent=d.status;
    document.getElementById('log').textContent=d.log.join('\\n');
    var logEl=document.getElementById('log');
    logEl.scrollTop=logEl.scrollHeight;
    if(d.done){
      document.getElementById('spin').style.display='none';
      if(d.error){
        document.getElementById('status').textContent='Ошибка: '+d.error;
        document.getElementById('status').style.color='#dc2626';
      } else {
        document.getElementById('status').textContent='Готово!';
        document.getElementById('status').style.color='#16a34a';
      }
    } else {
      setTimeout(poll,1000);
    }
  }).catch(()=>setTimeout(poll,2000));
}
poll();
</script>
</body>
</html>"""


# ── HTTP сервер ───────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_html(self, html, code=200):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        if self.path == "/":
            login, _ = load_credentials()
            if login:
                self.redirect("/go")
            else:
                self.send_html(LOGIN_HTML)

        elif self.path == "/go":
            _state.update({"log": [], "done": False, "error": None, "result_file": None})
            login, password = load_credentials()
            threading.Thread(target=download_tickets, args=(login, password), daemon=True).start()
            self.send_html(PROGRESS_HTML)

        elif self.path == "/status":
            body = json.dumps({
                "status": _state["status"],
                "log": _state["log"],
                "done": _state["done"],
                "error": _state["error"],
                "result_file": _state["result_file"],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/reset":
            if CONF_FILE.exists():
                CONF_FILE.unlink()
            self.redirect("/")

        else:
            self.send_html("<h1>404</h1>", 404)

    def do_POST(self):
        if self.path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            params = urllib.parse.parse_qs(self.rfile.read(length).decode())
            login = params.get("login", [""])[0].strip()
            password = params.get("password", [""])[0].strip()

            if login and password:
                save_credentials(login, password)
                _state.update({"log": [], "done": False, "error": None, "result_file": None})
                threading.Thread(target=download_tickets, args=(login, password), daemon=True).start()
                self.send_html(PROGRESS_HTML)
            else:
                self.redirect("/")


def _stop_when_done():
    while not _state["done"]:
        time.sleep(1)
    time.sleep(5)
    if _server:
        threading.Thread(target=_server.shutdown, daemon=True).start()
    subprocess.Popen(["pkill", "-f", "rw-ticket.py"])


def main():
    global _server
    _server = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    def open_browser(url):
        try:
            subprocess.Popen(["termux-open-url", url])
        except Exception:
            webbrowser.open(url)
    threading.Timer(0.5, lambda: open_browser(f"http://localhost:{PORT}/")).start()
    threading.Thread(target=_stop_when_done, daemon=True).start()
    print(f"Открываю браузер: http://localhost:{PORT}/")
    try:
        _server.serve_forever()
    except KeyboardInterrupt:
        pass
    print("Готово.")


if __name__ == "__main__":
    main()
