"""
IAP — Innovation Assessment Platform
Flask App for Web Deployment (Secured)
"""

from flask import Flask, request, jsonify, send_from_directory, abort
from functools import wraps
import os
import json
import html
import time
from collections import defaultdict
from database import init_db, save_attempt, get_all_attempts, get_stats, delete_attempt, delete_all_attempts

# ── Setup ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 🔴 Fix #1: لا نستخدم static_folder لمنع تسريب الملفات
app = Flask(__name__)

init_db()

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# ── Fix #3: كلمة مرور للحذف ──────────────────────────────────────────────────
REPORT_PASSWORD = os.environ.get("REPORT_PASSWORD", "admin2024")

# ── Fix #8: مجموعة التسميات الصالحة ──────────────────────────────────────────
VALID_LABELS = set()
for q in CONFIG["questions"]:
    for opt in q["options"]:
        VALID_LABELS.add(opt["label"])

# ── Fix #10: Rate Limiting بسيط ──────────────────────────────────────────────
_rate_store = defaultdict(list)
RATE_LIMIT = 30
RATE_WINDOW = 60

def _check_rate(ip):
    now = time.time()
    _rate_store[ip] = [t for t in _rate_store[ip] if now - t < RATE_WINDOW]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        return False
    _rate_store[ip].append(now)
    return True

def rate_limited(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        ip = request.remote_addr or '0.0.0.0'
        if not _check_rate(ip):
            return jsonify({"error": "طلبات كثيرة جداً. انتظر قليلاً."}), 429
        return f(*args, **kwargs)
    return wrapped


# ── Fix #9: تعقيم HTML ───────────────────────────────────────────────────────
def _sanitize(text):
    return html.escape(text.strip(), quote=True)[:200]


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
        return None
    for i, s in enumerate(scores):
        if s == min_score:
            return CONFIG["skills"][i]
    return CONFIG["skills"][0]


# ── Fix #3: تحقق من المصادقة للحذف ───────────────────────────────────────────
def _check_auth():
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {REPORT_PASSWORD}":
        return True
    if request.args.get("key") == REPORT_PASSWORD:
        return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Routes — ملفات ثابتة (Fix #1: فقط index.html و report.html)
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/index.html')
def index_html():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/logo-ai.svg')
def logo_ai():
    return send_from_directory(BASE_DIR, 'logo-ai.svg')


@app.route('/report.html')
def report():
    return send_from_directory(BASE_DIR, 'report.html')


# 🔴 منع الوصول لأي ملف آخر (config.json, iap.db, server.py, etc.)
@app.route('/<path:path>')
def catch_all(path):
    # API routes تمر عبر مسارات أخرى
    if not path.startswith('api/'):
        abort(404)


# ══════════════════════════════════════════════════════════════════════════════
# Routes — APIs
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/api/questions')
@rate_limited
def get_questions():
    questions = []
    for q in CONFIG["questions"]:
        questions.append({
            "id": q["id"],
            "skill_key": q["skill_key"],
            "text": q["text"],
            "options": [{"label": o["label"], "text": o["text"]} for o in q["options"]]
        })
    return jsonify({"questions": questions})


@app.route('/api/submit', methods=['POST'])
@rate_limited
def submit():
    data = request.get_json()
    if not data:
        return jsonify({"error": "بيانات غير صالحة"}), 400

    # Fix #9: تعقيم الاسم
    full_name = _sanitize(data.get("full_name", ""))
    answers = data.get("answers", {})

    if not full_name or len(full_name) < 5:
        return jsonify({"error": "الاسم الثلاثي مطلوب"}), 400

    if len(answers) != 5:
        return jsonify({"error": "يجب الإجابة على جميع الأسئلة الخمسة"}), 400

    # Fix #8: تحقق من صحة labels
    for qid in ["1", "2", "3", "4", "5"]:
        label = answers.get(qid, "")
        if label not in VALID_LABELS:
            return jsonify({"error": f"إجابة غير صالحة للسؤال {qid}"}), 400

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

    # Fix #7: التعامل مع درجات متساوية
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
    return jsonify(result)


@app.route('/api/stats')
@rate_limited
def stats():
    return jsonify(get_stats())


@app.route('/api/attempts')
@rate_limited
def attempts():
    limit = request.args.get('limit', 500, type=int)
    return jsonify({"attempts": get_all_attempts(limit)})


# ── Fix #2 + Fix #3: حذف مع مصادقة ──────────────────────────────────────────
@app.route('/api/attempts/<int:attempt_id>', methods=['DELETE'])
@rate_limited
def delete_single(attempt_id):
    if not _check_auth():
        return jsonify({"error": "غير مصرح"}), 401
    delete_attempt(attempt_id)
    return jsonify({"success": True})


@app.route('/api/attempts/all', methods=['DELETE'])
@rate_limited
def delete_all():
    if not _check_auth():
        return jsonify({"error": "غير مصرح"}), 401
    delete_all_attempts()
    return jsonify({"success": True})


# ══════════════════════════════════════════════════════════════════════════════
# Run
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("""
 ============================================
   IAP - Innovation Assessment Platform
 ============================================
   http://localhost:8090
   http://localhost:8090/report.html
   Ctrl+C to stop
 ============================================
""")
    app.run(host='0.0.0.0', port=8090, debug=False)
