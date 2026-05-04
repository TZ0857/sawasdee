from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import os

from sqlalchemy import select, text
from app.database import init_db, async_session, engine
from app.models.user import User
from app.seed import (
    generate_seed_users, generate_seed_posts,
    generate_seed_albums, generate_seed_stories,
    generate_seed_gatherings,
)
from app.routers import auth, users, posts, messages, albums, subscriptions, gatherings


async def run_lightweight_migrations():
    """Idempotent ALTER TABLE statements for schema changes that
    create_all() cannot apply (it only handles new tables).
    Each statement is wrapped in IF NOT EXISTS / DROP NOT NULL semantics
    so re-running on an already-migrated DB is a no-op."""
    statements = [
        # posts.content was NOT NULL — make it optional so a post can be
        # image-only, audio-only, or video-only.
        "ALTER TABLE posts ALTER COLUMN content DROP NOT NULL",
        # posts.audio_url is the voice-message column.
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS audio_url VARCHAR(500) DEFAULT ''",
        # posts.video_url is the short-video column.
        "ALTER TABLE posts ADD COLUMN IF NOT EXISTS video_url VARCHAR(500) DEFAULT ''",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                # Don't crash the app if a migration fails (e.g. column
                # already in the desired state on a fresh DB).
                print(f"[migration] skipped: {stmt.split()[2:6]} → {e}")


async def seed_demo_data():
    """Populate database with demo data if empty."""
    async with async_session() as session:
        result = await session.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # Already has data

        print("🌱 Seeding demo data...")
        seed_users = generate_seed_users()
        for u in seed_users:
            session.add(u)
        await session.flush()

        seed_posts = generate_seed_posts(seed_users)
        for p in seed_posts:
            session.add(p)

        seed_albums, seed_photos = generate_seed_albums(seed_users)
        for a in seed_albums:
            session.add(a)
        await session.flush()
        for ph in seed_photos:
            session.add(ph)

        seed_stories = generate_seed_stories(seed_users)
        for s in seed_stories:
            session.add(s)

        seed_g, seed_gm = generate_seed_gatherings(seed_users)
        for g in seed_g:
            session.add(g)
        await session.flush()
        for gm in seed_gm:
            session.add(gm)

        await session.commit()
        print(f"✅ Seeded {len(seed_users)} users, {len(seed_posts)} posts, {len(seed_albums)} albums, {len(seed_stories)} stories, {len(seed_g)} gatherings")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await run_lightweight_migrations()
    await seed_demo_data()
    yield


app = FastAPI(title="Sawasdee", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def add_security_headers(request, call_next):
    """Forbid browsers/proxies from caching authenticated pages and API
    responses. Without this, a stale HTML or JSON response could be
    served to a different user (or the original user on a shared device)
    out of disk cache.

    Static assets under /static/ and /uploads/ are intentionally cacheable
    (no user data) — the StaticFiles mounts handle them before this
    middleware runs the response, but we still skip them defensively.
    """
    response = await call_next(request)
    path = request.url.path
    if not (path.startswith("/static/") or path.startswith("/uploads/")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        # Lightweight defence-in-depth headers
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


# Mount static files and uploads
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(uploads_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

templates = Jinja2Templates(directory=templates_dir)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(messages.router)
app.include_router(albums.router)
app.include_router(subscriptions.router)
app.include_router(gatherings.router)


# Page routes
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("pages/landing.html", {"request": request})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("pages/login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("pages/register.html", {"request": request})


@app.get("/explore", response_class=HTMLResponse)
async def explore_page(request: Request):
    return templates.TemplateResponse("pages/explore.html", {"request": request})


@app.get("/feed", response_class=HTMLResponse)
async def feed_page(request: Request):
    return templates.TemplateResponse("pages/feed.html", {"request": request})


@app.get("/profile", response_class=HTMLResponse)
async def profile_redirect(request: Request):
    """Redirect /profile to the logged-in user's own profile via JS (token lives in localStorage)."""
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh-TW"><head>
<meta charset="UTF-8"><title>Sawasdee</title>
<style>body{background:#0a0a0a;color:#B8B0A0;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}</style>
</head><body>
<p>跳轉中…</p>
<script>
  try {
    const u = JSON.parse(localStorage.getItem('user') || '{}');
    if (u && u.username) location.replace('/profile/' + u.username);
    else location.replace('/login');
  } catch (e) { location.replace('/login'); }
</script>
</body></html>""")


@app.get("/profile/{username}", response_class=HTMLResponse)
async def profile_page(request: Request, username: str):
    return templates.TemplateResponse("pages/profile.html", {"request": request, "username": username})


@app.get("/messages", response_class=HTMLResponse)
async def messages_page(request: Request):
    return templates.TemplateResponse("pages/messages.html", {"request": request})


@app.get("/chat/{user_id}", response_class=HTMLResponse)
async def chat_page(request: Request, user_id: str):
    return templates.TemplateResponse("pages/chat.html", {"request": request, "user_id": user_id})


@app.get("/gatherings", response_class=HTMLResponse)
async def gatherings_page(request: Request):
    return templates.TemplateResponse("pages/gatherings.html", {"request": request})


@app.get("/gatherings/{gathering_id}/chat", response_class=HTMLResponse)
async def gathering_chat_page(request: Request, gathering_id: str):
    return templates.TemplateResponse(
        "pages/gathering_chat.html",
        {"request": request, "gathering_id": gathering_id},
    )


@app.get("/subscription", response_class=HTMLResponse)
async def subscription_page(request: Request):
    return templates.TemplateResponse("pages/subscription.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("pages/settings.html", {"request": request})
