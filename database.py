"""
IAP — Innovation Assessment Platform
Database Module (SQLite)
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iap.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """إنشاء الجداول — يحذف الهيكل القديم تلقائياً عند التحديث"""
    conn = _conn()
    # فحص إذا كان الهيكل القديم موجوداً (جدول subscribers)
    old = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subscribers'").fetchone()
    if old:
        conn.executescript("DROP TABLE IF EXISTS attempts; DROP TABLE IF EXISTS subscribers;")
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


def save_attempt(full_name, answers_text, scores, total_score, innovation_title, development_skill, recommendation_text):
    """حفظ محاولة التقييم"""
    conn = _conn()
    conn.execute(
        """INSERT INTO attempts
           (full_name, q1_answer, q2_answer, q3_answer, q4_answer, q5_answer,
            q1_score, q2_score, q3_score, q4_score, q5_score,
            total_score, innovation_title, development_skill, recommendation_text)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (full_name,
         answers_text[0], answers_text[1], answers_text[2], answers_text[3], answers_text[4],
         scores[0], scores[1], scores[2], scores[3], scores[4],
         total_score, innovation_title, development_skill, recommendation_text)
    )
    conn.commit()
    conn.close()


def get_all_attempts(limit=500):
    """جلب كل المحاولات"""
    conn = _conn()
    rows = conn.execute("""
        SELECT * FROM attempts ORDER BY created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    """إحصائيات عامة"""
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) as c FROM attempts").fetchone()["c"]
    avg = conn.execute("SELECT COALESCE(AVG(total_score),0) as a FROM attempts").fetchone()["a"]

    titles = conn.execute("""
        SELECT innovation_title, COUNT(*) as c
        FROM attempts GROUP BY innovation_title
    """).fetchall()

    skills = conn.execute("""
        SELECT development_skill, COUNT(*) as c
        FROM attempts GROUP BY development_skill
        ORDER BY c DESC
    """).fetchall()

    conn.close()
    return {
        "total_attempts": total,
        "average_score": round(avg, 1),
        "titles_distribution": {r["innovation_title"]: r["c"] for r in titles},
        "skills_needing_development": [{"skill": r["development_skill"], "count": r["c"]} for r in skills]
    }
