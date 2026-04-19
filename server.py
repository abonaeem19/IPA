"""
IAP — Innovation Assessment Platform
Server Module (Secured)
تشغيل: python server.py
الواجهة: http://localhost:8090
التقارير: http://localhost:8090/report.html
"""

# ── 🟠 Fix #4: Windows Unicode crash ─────────────────────────────────────────
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import http.server
import socketserver
import os
import json
import html
import time
import hashlib
import urllib.parse
from collections import defaultdict
from database import init_db, save_attempt, get_all_attempts, get_stats, delete_attempt, delete_all_attempts

PORT = 8090
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
init_db()

# ── 🔴 Fix #3: كلمة مرور للشيت المركزي ───────────────────────────────────────
# غيّرها حسب حاجتك — تُستخدم في report.html فقط
REPORT_PASSWORD = os.environ.get("REPORT_PASSWORD", "admin2024")

# ── 🔴 Fix #1: قائمة الملفات المسموح تقديمها فقط ─────────────────────────────
ALLOWED_FILES = {
    "/index.html": ("text/html; charset=utf-8", "index.html"),
    "/report.html": ("text/html; charset=utf-8", "report.html"),
    "/logo-ai.svg": ("image/svg+xml", "logo-ai.svg"),
}

# ── 🟠 Fix #10: Rate Limiting بسيط ───────────────────────────────────────────
_rate_store = defaultdict(list)
RATE_LIMIT = 30       # طلبات
RATE_WINDOW = 60      # ثانية

def _check_rate(ip):
    now = time.time()
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        return False
    _rate_store[ip].append(now)
    return True

# ── تحميل الإعدادات ──────────────────────────────────────────────────────────
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# ── Fix #8: مجموعة التسميات الصالحة للإجابات ─────────────────────────────────
VALID_LABELS = set()
for q in CONFIG["questions"]:
    for opt in q["options"]:
        VALID_LABELS.add(opt["label"])


def _get_title(total_score):
    for t in CONFIG["titles"]:
        if t["min_score"] <= total_score <= t["max_score"]:
            return t
    return CONFIG["titles"][-1]


# ── Fix #7: المهارة الأضعف — لا تظهر عند الدرجة الكاملة ──────────────────────
def _get_weakest_skill(scores):
    min_score = min(scores)
    max_score = max(scores)
    if min_score == max_score:
        return None  # جميع الدرجات متساوية — لا مهارة أضعف
    for i, s in enumerate(scores):
        if s == min_score:
            return CONFIG["skills"][i]
    return CONFIG["skills"][0]


# ── Fix #9: تعقيم HTML في الاسم ──────────────────────────────────────────────
def _sanitize(text):
    return html.escape(text.strip(), quote=True)[:200]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _json(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw) if raw else {}


def _serve_file(handler, filepath, content_type):
    """تقديم ملف محدد فقط"""
    full = os.path.join(BASE_DIR, filepath)
    if not os.path.isfile(full):
        handler.send_error(404, "Not Found")
        return
    with open(full, "rb") as f:
        content = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(content)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(content)


def _check_auth(handler):
    """🔴 Fix #3: فحص كلمة المرور للتقارير (Bearer token بسيط)"""
    auth = handler.headers.get("Authorization", "")
    if auth == f"Bearer {REPORT_PASSWORD}":
        return True
    # أيضاً نقبل query param للمتصفح
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(handler.path).query)
    if qs.get("key", [""])[0] == REPORT_PASSWORD:
        return True
    return False


# ── Handler ───────────────────────────────────────────────────────────────────
# 🔴 Fix #1: نرث من BaseHTTPRequestHandler بدل SimpleHTTPRequestHandler
# لمنع تقديم أي ملف عشوائي (مثل iap.db أو server.py)
class IAPHandler(http.server.BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        ip = self.client_address[0]

        # Rate limiting
        if not _check_rate(ip):
            return _json(self, {"error": "طلبات كثيرة جداً. انتظر قليلاً."}, 429)

        # ── الجذر → index.html ──
        if path in ("/", ""):
            return _serve_file(self, "index.html", "text/html; charset=utf-8")

        # ── ملفات مسموحة فقط (Fix #1) ──
        if path in ALLOWED_FILES:
            ct, fp = ALLOWED_FILES[path]
            return _serve_file(self, fp, ct)

        # ── APIs ──
        if path == "/api/questions":
            questions = []
            for q in CONFIG["questions"]:
                questions.append({
                    "id": q["id"],
                    "skill_key": q["skill_key"],
                    "text": q["text"],
                    "options": [{"label": o["label"], "text": o["text"]} for o in q["options"]]
                })
            return _json(self, {"questions": questions})

        if path == "/api/stats":
            return _json(self, get_stats())

        if path == "/api/attempts":
            return _json(self, {"attempts": get_all_attempts()})

        # ── كل شيء آخر → 404 (لا تسريب) ──
        self.send_error(404, "Not Found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        ip = self.client_address[0]

        if not _check_rate(ip):
            return _json(self, {"error": "طلبات كثيرة جداً. انتظر قليلاً."}, 429)

        if path == "/api/submit":
            data = _body(self)

            # Fix #9: تعقيم الاسم
            full_name = _sanitize(data.get("full_name", ""))
            answers = data.get("answers", {})

            if not full_name or len(full_name) < 5:
                return _json(self, {"error": "الاسم الثلاثي مطلوب"}, 400)

            if len(answers) != 5:
                return _json(self, {"error": "يجب الإجابة على جميع الأسئلة الخمسة"}, 400)

            # Fix #8: تحقق من صحة labels
            for qid in ["1", "2", "3", "4", "5"]:
                label = answers.get(qid, "")
                if label not in VALID_LABELS:
                    return _json(self, {"error": f"إجابة غير صالحة للسؤال {qid}"}, 400)

            scores = []
            answers_text = []
            for q in CONFIG["questions"]:
                qid = str(q["id"])
                answer_label = answers.get(qid, "")
                score = 1
                answer_t = ""
                for opt in q["options"]:
                    if opt["label"] == answer_label:
                        score = opt["score"]
                        answer_t = opt["text"]
                        break
                scores.append(score)
                answers_text.append(answer_t)

            total = sum(scores)
            title_info = _get_title(total)
            skill_info = _get_weakest_skill(scores)

            # Fix #7: إذا جميع الدرجات متساوية — لا مهارة أضعف
            if skill_info is None:
                skill_name = "متوازن في جميع المهارات"
                recommendation = "أنت متوازن في جميع المهارات الابتكارية. استمر في تطوير مهاراتك بشكل شامل."
            else:
                skill_name = skill_info["name_ar"]
                recommendation = skill_info["recommendation"]

            save_attempt(
                full_name, answers_text, scores, total,
                title_info["name_ar"], skill_name, recommendation
            )

            result = {
                "subscriber_name": full_name,
                "scores": scores,
                "total_score": total,
                "max_score": 15,
                "innovation_title": title_info["name_ar"],
                "title_description": title_info["description"],
                "development_skill": skill_name,
                "recommendation": recommendation,
                "result_text": f'دورك في العملية الابتكارية هو: {title_info["name_ar"]}.'
                    + (f' ولتعزيز قدراتك ننصحك بالتركيز على {skill_name}.' if skill_info else '')
            }
            return _json(self, result)

        _json(self, {"error": "مسار غير موجود"}, 404)

    # ── 🔴 Fix #2: دعم DELETE ─────────────────────────────────────────────────
    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        ip = self.client_address[0]

        if not _check_rate(ip):
            return _json(self, {"error": "طلبات كثيرة جداً."}, 429)

        # Fix #3: فحص المصادقة
        if not _check_auth(self):
            return _json(self, {"error": "غير مصرح"}, 401)

        # حذف محاولة واحدة
        if path.startswith("/api/attempts/") and path != "/api/attempts/all":
            try:
                attempt_id = int(path.split("/")[-1])
                delete_attempt(attempt_id)
                return _json(self, {"success": True})
            except (ValueError, IndexError):
                return _json(self, {"error": "معرّف غير صالح"}, 400)

        # حذف الكل
        if path == "/api/attempts/all":
            delete_all_attempts()
            return _json(self, {"success": True})

        _json(self, {"error": "مسار غير موجود"}, 404)

    def log_message(self, fmt, *args):
        try:
            status = args[1] if len(args) > 1 else "???"
            color = "\033[92m" if str(status).startswith("2") else \
                    "\033[93m" if str(status).startswith("3") else "\033[91m"
            print(f"  {color}[{self.address_string()}] {fmt % args}\033[0m")
        except Exception:
            pass  # تجنب أي خطأ encoding في الطباعة


# ── 🟠 Fix #5: ThreadingHTTPServer بدل TCPServer ─────────────────────────────
class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("""
 ============================================
   IAP - Innovation Assessment Platform
 ============================================
   http://localhost:8090
   http://localhost:8090/report.html
   Ctrl+C to stop
 ============================================
""")
    with ThreadedServer(("", PORT), IAPHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")
