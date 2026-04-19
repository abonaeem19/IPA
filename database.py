"""
IAP — Innovation Assessment Platform
Database Module — PostgreSQL (Supabase) with SQLite fallback

الأولوية:
1. إذا وُجد DATABASE_URL → يحاول PostgreSQL
2. إذا وُجدت متغيرات منفصلة (DB_HOST, DB_PASS) → يبني الرابط ويحاول PostgreSQL
3. إذا فشل أي شيء → يرجع لـ SQLite تلقائياً (مع تحذير)
"""

import os
import json
import traceback
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
# تحديد نوع قاعدة البيانات تلقائياً
# ══════════════════════════════════════════════════════════════════════════════

_use_pg = False
_pg_dsn = None
_pg_error = None

# محاولة 1: DATABASE_URL
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# محاولة 2: متغيرات منفصلة (أسهل للمستخدم)
DB_HOST = os.environ.get("DB_HOST", "").strip()
DB_USER = os.environ.get("DB_USER", "").strip()
DB_PASS = os.environ.get("DB_PASS", "").strip()
DB_PORT = os.environ.get("DB_PORT", "6543").strip()
DB_NAME = os.environ.get("DB_NAME", "postgres").strip()

if DATABASE_URL:
    _pg_dsn = DATABASE_URL
elif DB_HOST and DB_PASS:
    # بناء الرابط من المتغيرات المنفصلة
    if not DB_USER:
        DB_USER = "postgres"
    _pg_dsn = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

if _pg_dsn:
    try:
        import psycopg2
        import psycopg2.extras
        # اختبار الاتصال فوراً
        test_conn = psycopg2.connect(_pg_dsn)
        test_conn.close()
        _use_pg = True
        print(f"  [DB] PostgreSQL connected successfully")
    except Exception as e:
        _pg_error = str(e)
        _use_pg = False
        print(f"  [DB] PostgreSQL FAILED: {e}")
        print(f"  [DB] Falling back to SQLite...")

if not _use_pg:
    import sqlite3
    print(f"  [DB] Using SQLite (local storage)")


# ══════════════════════════════════════════════════════════════════════════════
# PostgreSQL Implementation
# ══════════════════════════════════════════════════════════════════════════════

if _use_pg:
    import psycopg2
    import psycopg2.extras

    def _conn():
        conn = psycopg2.connect(_pg_dsn)
        conn.autocommit = False
        return conn

    def init_db():
        try:
            conn = _conn()
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS attempts (
                    id                  SERIAL PRIMARY KEY,
                    full_name           TEXT NOT NULL,
                    q1_answer           TEXT NOT NULL,
                    q2_answer           TEXT NOT NULL,
                    q3_answer           TEXT NOT NULL,
                    q4_answer           TEXT NOT NULL,
                    q5_answer           TEXT NOT NULL,
                    q1_score            INTEGER NOT NULL,
                    q2_score            INTEGER NOT NULL,
                    q3_score            INTEGER NOT NULL,
                    q4_score            INTEGER NOT NULL,
                    q5_score            INTEGER NOT NULL,
                    total_score         INTEGER NOT NULL,
                    innovation_title    TEXT NOT NULL,
                    development_skill   TEXT NOT NULL,
                    recommendation_text TEXT NOT NULL,
                    created_at          TIMESTAMP DEFAULT NOW()
                );
            """)
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"  [DB] init_db error: {e}")

    def save_attempt(full_name, answers_text, scores, total_score,
                     innovation_title, development_skill, recommendation_text):
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO attempts
               (full_name, q1_answer, q2_answer, q3_answer, q4_answer, q5_answer,
                q1_score, q2_score, q3_score, q4_score, q5_score,
                total_score, innovation_title, development_skill, recommendation_text)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (full_name,
             answers_text[0], answers_text[1], answers_text[2],
             answers_text[3], answers_text[4],
             scores[0], scores[1], scores[2], scores[3], scores[4],
             total_score, innovation_title, development_skill, recommendation_text)
        )
        conn.commit()
        cur.close()
        conn.close()

    def get_all_attempts(limit=500):
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM attempts ORDER BY created_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for r in rows:
            d = dict(r)
            if d.get('created_at'):
                d['created_at'] = d['created_at'].isoformat()
            result.append(d)
        return result

    def delete_attempt(attempt_id):
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM attempts WHERE id = %s", (attempt_id,))
        conn.commit()
        cur.close()
        conn.close()

    def delete_all_attempts():
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM attempts")
        conn.commit()
        cur.close()
        conn.close()

    def get_stats():
        conn = _conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT COUNT(*) as c FROM attempts")
        total = cur.fetchone()["c"]
        cur.execute("SELECT COALESCE(AVG(total_score),0) as a FROM attempts")
        avg = float(cur.fetchone()["a"])
        cur.execute("SELECT innovation_title, COUNT(*) as c FROM attempts GROUP BY innovation_title")
        titles = cur.fetchall()
        cur.execute("SELECT development_skill, COUNT(*) as c FROM attempts GROUP BY development_skill ORDER BY c DESC")
        skills = cur.fetchall()
        cur.close()
        conn.close()
        return {
            "total_attempts": total,
            "average_score": round(avg, 1),
            "titles_distribution": {r["innovation_title"]: r["c"] for r in titles},
            "skills_needing_development": [{"skill": r["development_skill"], "count": r["c"]} for r in skills]
        }


# ══════════════════════════════════════════════════════════════════════════════
# SQLite Fallback
# ══════════════════════════════════════════════════════════════════════════════

else:
    DB_DIR = os.environ.get("DB_DIR", os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(DB_DIR, exist_ok=True)
    DB_PATH = os.path.join(DB_DIR, "iap.db")

    def _conn():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_db():
        conn = _conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS attempts (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name           TEXT NOT NULL,
                q1_answer           TEXT NOT NULL,
                q2_answer           TEXT NOT NULL,
                q3_answer           TEXT NOT NULL,
                q4_answer           TEXT NOT NULL,
                q5_answer           TEXT NOT NULL,
                q1_score            INTEGER NOT NULL,
                q2_score            INTEGER NOT NULL,
                q3_score            INTEGER NOT NULL,
                q4_score            INTEGER NOT NULL,
                q5_score            INTEGER NOT NULL,
                total_score         INTEGER NOT NULL,
                innovation_title    TEXT NOT NULL,
                development_skill   TEXT NOT NULL,
                recommendation_text TEXT NOT NULL,
                created_at          TEXT DEFAULT (datetime('now','localtime'))
            );
        """)
        conn.commit()
        conn.close()

    def save_attempt(full_name, answers_text, scores, total_score,
                     innovation_title, development_skill, recommendation_text):
        conn = _conn()
        conn.execute(
            """INSERT INTO attempts
               (full_name, q1_answer, q2_answer, q3_answer, q4_answer, q5_answer,
                q1_score, q2_score, q3_score, q4_score, q5_score,
                total_score, innovation_title, development_skill, recommendation_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (full_name,
             answers_text[0], answers_text[1], answers_text[2],
             answers_text[3], answers_text[4],
             scores[0], scores[1], scores[2], scores[3], scores[4],
             total_score, innovation_title, development_skill, recommendation_text)
        )
        conn.commit()
        conn.close()

    def get_all_attempts(limit=500):
        conn = _conn()
        rows = conn.execute(
            "SELECT * FROM attempts ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_attempt(attempt_id):
        conn = _conn()
        conn.execute("DELETE FROM attempts WHERE id = ?", (attempt_id,))
        conn.commit()
        conn.close()

    def delete_all_attempts():
        conn = _conn()
        conn.execute("DELETE FROM attempts")
        conn.commit()
        conn.close()

    def get_stats():
        conn = _conn()
        total = conn.execute("SELECT COUNT(*) as c FROM attempts").fetchone()["c"]
        avg = conn.execute("SELECT COALESCE(AVG(total_score),0) as a FROM attempts").fetchone()["a"]
        titles = conn.execute("SELECT innovation_title, COUNT(*) as c FROM attempts GROUP BY innovation_title").fetchall()
        skills = conn.execute("SELECT development_skill, COUNT(*) as c FROM attempts GROUP BY development_skill ORDER BY c DESC").fetchall()
        conn.close()
        return {
            "total_attempts": total,
            "average_score": round(avg, 1),
            "titles_distribution": {r["innovation_title"]: r["c"] for r in titles},
            "skills_needing_development": [{"skill": r["development_skill"], "count": r["c"]} for r in skills]
        }
