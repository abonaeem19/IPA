"""
IAP — Innovation Assessment Platform
Flask App for Web Deployment (PythonAnywhere / Render / Railway)
"""

from flask import Flask, request, jsonify, send_from_directory
import os
import json
from database import init_db, save_attempt, get_all_attempts, get_stats, delete_attempt, delete_all_attempts

# ── Setup ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')

init_db()

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as f:
    CONFIG = json.load(f)


def _get_title(total_score):
    for t in CONFIG["titles"]:
        if t["min_score"] <= total_score <= t["max_score"]:
            return t
    return CONFIG["titles"][-1]


def _get_weakest_skill(scores):
    min_score = min(scores)
    for i, s in enumerate(scores):
        if s == min_score:
            return CONFIG["skills"][i]
    return CONFIG["skills"][0]


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/report.html')
def report():
    return send_from_directory(BASE_DIR, 'report.html')


@app.route('/api/questions')
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
def submit():
    data = request.get_json()

    full_name = data.get("full_name", "").strip()
    answers = data.get("answers", {})

    if not full_name:
        return jsonify({"error": "الاسم الثلاثي مطلوب"}), 400

    if len(answers) != 5:
        return jsonify({"error": "يجب الإجابة على جميع الأسئلة الخمسة"}), 400

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

    save_attempt(
        full_name, answers_text, scores, total,
        title_info["name_ar"],
        skill_info["name_ar"],
        skill_info["recommendation"]
    )

    result = {
        "subscriber_name": full_name,
        "scores": scores,
        "total_score": total,
        "max_score": 15,
        "innovation_title": title_info["name_ar"],
        "title_description": title_info["description"],
        "development_skill": skill_info["name_ar"],
        "recommendation": skill_info["recommendation"],
        "result_text": f'دورك في العملية الابتكارية هو: {title_info["name_ar"]}. ولتعزيز قدراتك ننصحك بالتركيز على {skill_info["name_ar"]}.'
    }
    return jsonify(result)


@app.route('/api/stats')
def stats():
    return jsonify(get_stats())


@app.route('/api/attempts')
def attempts():
    limit = request.args.get('limit', 500, type=int)
    return jsonify({"attempts": get_all_attempts(limit)})


@app.route('/api/attempts/<int:attempt_id>', methods=['DELETE'])
def delete_single(attempt_id):
    delete_attempt(attempt_id)
    return jsonify({"success": True})


@app.route('/api/attempts/all', methods=['DELETE'])
def delete_all():
    delete_all_attempts()
    return jsonify({"success": True})


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("""
╔══════════════════════════════════════════╗
║   💡  IAP — مقياس الابتكار (Flask)       ║
╠══════════════════════════════════════════╣
║   🌐  http://localhost:8090              ║
║   📊  http://localhost:8090/report.html  ║
║   🛑  Ctrl+C للإيقاف                    ║
╚══════════════════════════════════════════╝
""")
    app.run(host='0.0.0.0', port=8090, debug=False)
