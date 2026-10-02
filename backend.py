"""Signal Harvest API: SQLite storage and authorised Reddit collection."""
import csv
import io
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import praw
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()
ROOT = Path(__file__).parent
DB_PATH = ROOT / "signal_harvest.db"
app = FastAPI(title="Signal Harvest")


@contextmanager
def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def setup_database():
    with db() as connection:
        connection.executescript("""
        CREATE TABLE IF NOT EXISTS targets (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, platform TEXT NOT NULL DEFAULT 'reddit',
          subreddits TEXT NOT NULL, include_keywords TEXT NOT NULL DEFAULT '', exclude_keywords TEXT NOT NULL DEFAULT '',
          sort TEXT NOT NULL DEFAULT 'new', time_filter TEXT NOT NULL DEFAULT 'week', paused INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS posts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, reddit_id TEXT NOT NULL UNIQUE, target_id INTEGER NOT NULL,
          subreddit TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', author TEXT, url TEXT NOT NULL,
          score INTEGER NOT NULL DEFAULT 0, num_comments INTEGER NOT NULL DEFAULT 0, created_utc TEXT NOT NULL,
          matched_keywords TEXT NOT NULL DEFAULT '', fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE
        );
        """)


@app.on_event("startup")
def startup():
    setup_database()


class TargetInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    platform: Literal["reddit"] = "reddit"
    subreddits: str = Field(min_length=1, max_length=500)
    include_keywords: str = Field(default="", max_length=500)
    exclude_keywords: str = Field(default="", max_length=500)
    sort: Literal["new", "hot", "top", "rising"] = "new"
    time_filter: Literal["hour", "day", "week", "month", "year", "all"] = "week"
    paused: bool = False


def target_dict(row):
    item = dict(row)
    item["paused"] = bool(item["paused"])
    item["subreddit_list"] = [part.strip().removeprefix("r/") for part in item["subreddits"].split(",") if part.strip()]
    return item


@app.get("/api/targets")
def list_targets():
    with db() as connection:
        rows = connection.execute("SELECT * FROM targets ORDER BY updated_at DESC, id DESC").fetchall()
    return [target_dict(row) for row in rows]


@app.post("/api/targets", status_code=201)
def create_target(target: TargetInput):
    with db() as connection:
        cursor = connection.execute("""INSERT INTO targets (name,platform,subreddits,include_keywords,exclude_keywords,sort,time_filter,paused)
          VALUES (?,?,?,?,?,?,?,?)""", (target.name.strip(), target.platform, target.subreddits.strip(), target.include_keywords.strip(), target.exclude_keywords.strip(), target.sort, target.time_filter, target.paused))
        row = connection.execute("SELECT * FROM targets WHERE id=?", (cursor.lastrowid,)).fetchone()
    return target_dict(row)


@app.put("/api/targets/{target_id}")
def update_target(target_id: int, target: TargetInput):
    with db() as connection:
        found = connection.execute("SELECT id FROM targets WHERE id=?", (target_id,)).fetchone()
        if not found: raise HTTPException(404, "Target not found")
        connection.execute("""UPDATE targets SET name=?,platform=?,subreddits=?,include_keywords=?,exclude_keywords=?,sort=?,time_filter=?,paused=?,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
          (target.name.strip(), target.platform, target.subreddits.strip(), target.include_keywords.strip(), target.exclude_keywords.strip(), target.sort, target.time_filter, target.paused, target_id))
        row = connection.execute("SELECT * FROM targets WHERE id=?", (target_id,)).fetchone()
    return target_dict(row)


@app.delete("/api/targets/{target_id}", status_code=204)
def delete_target(target_id: int):
    with db() as connection:
        connection.execute("DELETE FROM posts WHERE target_id=?", (target_id,))
        if connection.execute("DELETE FROM targets WHERE id=?", (target_id,)).rowcount == 0: raise HTTPException(404, "Target not found")


def reddit_client():
    keys = [os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET"), os.getenv("REDDIT_USER_AGENT")]
    if not all(keys): raise HTTPException(400, "Reddit credentials are missing. Copy .env.example to .env and add your Reddit script-app credentials.")
    return praw.Reddit(client_id=keys[0], client_secret=keys[1], user_agent=keys[2])


def words(text): return [word.strip().lower() for word in text.split(",") if word.strip()]


def within_time_filter(created_utc, time_filter):
    """Apply the selected period to listing types where Reddit has no time parameter."""
    periods = {"hour": 3600, "day": 86400, "week": 604800, "month": 2592000, "year": 31536000}
    return time_filter == "all" or created_utc >= datetime.now(timezone.utc).timestamp() - periods[time_filter]


def fetch_target(target):
    reddit = reddit_client(); inserted = 0
    includes, excludes = words(target["include_keywords"]), words(target["exclude_keywords"])
    method = getattr(reddit.subreddit("+").join(target_dict(target)["subreddit_list"]), target["sort"])
    try: listing = method(limit=100, time_filter=target["time_filter"]) if target["sort"] == "top" else method(limit=100)
    except Exception as error: raise HTTPException(502, f"Reddit collection failed: {error}")
    with db() as connection:
        for post in listing:
            if not within_time_filter(post.created_utc, target["time_filter"]): continue
            content = f"{post.title} {post.selftext}".lower()
            matched = [word for word in includes if word in content]
            if (includes and not matched) or any(word in content for word in excludes): continue
            result = connection.execute("""INSERT OR IGNORE INTO posts (reddit_id,target_id,subreddit,title,body,author,url,score,num_comments,created_utc,matched_keywords)
              VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (post.id, target["id"], str(post.subreddit), post.title, post.selftext or "", str(post.author or "[deleted]"), f"https://www.reddit.com{post.permalink}", post.score, post.num_comments, datetime.fromtimestamp(post.created_utc, timezone.utc).isoformat(), ", ".join(matched)))
            inserted += result.rowcount
    return inserted


@app.post("/api/fetch")
def fetch_all():
    with db() as connection: targets = connection.execute("SELECT * FROM targets WHERE paused=0").fetchall()
    total = sum(fetch_target(target) for target in targets)
    return {"inserted": total, "targets_checked": len(targets)}


@app.post("/api/targets/{target_id}/fetch")
def fetch_one(target_id: int):
    with db() as connection: target = connection.execute("SELECT * FROM targets WHERE id=?", (target_id,)).fetchone()
    if not target: raise HTTPException(404, "Target not found")
    if target["paused"]: raise HTTPException(400, "Resume this target before fetching it")
    return {"inserted": fetch_target(target), "targets_checked": 1}


def posts_query(target_id=None, keyword=None, after=None, min_score=0):
    sql = "SELECT posts.*, targets.name AS target_name FROM posts JOIN targets ON targets.id=posts.target_id WHERE score >= ?"; params = [min_score]
    if target_id: sql += " AND target_id=?"; params.append(target_id)
    if keyword: sql += " AND (lower(title) LIKE ? OR lower(body) LIKE ? OR lower(matched_keywords) LIKE ?)"; params += [f"%{keyword.lower()}%"] * 3
    if after: sql += " AND created_utc >= ?"; params.append(after + "T00:00:00")
    return sql + " ORDER BY created_utc DESC", params


@app.get("/api/posts")
def list_posts(target_id: int | None = None, keyword: str | None = None, after: str | None = None, min_score: int = Query(0, ge=0)):
    sql, params = posts_query(target_id, keyword, after, min_score)
    with db() as connection: return [dict(row) for row in connection.execute(sql, params).fetchall()]


@app.get("/api/posts/export")
def export_posts(target_id: int | None = None, keyword: str | None = None, after: str | None = None, min_score: int = Query(0, ge=0)):
    sql, params = posts_query(target_id, keyword, after, min_score)
    with db() as connection: rows = connection.execute(sql, params).fetchall()
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(["target", "subreddit", "title", "author", "score", "comments", "published", "matched_keywords", "url"])
    for row in rows: writer.writerow([row["target_name"], row["subreddit"], row["title"], row["author"], row["score"], row["num_comments"], row["created_utc"], row["matched_keywords"], row["url"]])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=signal-harvest-posts.csv"})


@app.get("/api/overview")
def overview():
    with db() as connection:
        targets = connection.execute("SELECT COUNT(*) FROM targets").fetchone()[0]
        active = connection.execute("SELECT COUNT(*) FROM targets WHERE paused=0").fetchone()[0]
        posts = connection.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        latest = connection.execute("SELECT fetched_at FROM posts ORDER BY fetched_at DESC LIMIT 1").fetchone()
    return {"targets": targets, "active_targets": active, "posts": posts, "last_fetch": latest[0] if latest else None}


@app.get("/")
def frontend(): return FileResponse(ROOT / "index.html")


app.mount("/", StaticFiles(directory=ROOT), name="static")
