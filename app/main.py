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
from app.routers import auth, users, posts, messages, albums, subscriptions, gatherings, blocks, notifications, translate, poll
# Import models so SQLAlchemy registers them on Base before init_db()
from app.models.block import BlockedUser  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.translation import MessageTranslation  # noqa: F401


# --- Demo avatar set ----------------------------------------------------
# Higher-quality portraits for the seed accounts. Replaces the older
# randomuser.me URLs that the user described as 「太低俗」. These are stable
# Unsplash photo URLs cropped to 400×400 face frames.
DEMO_AVATARS = {
    "ploy_bkk":     "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&h=400&fit=crop&crop=faces&q=80",
    "mintra_cm":    "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400&h=400&fit=crop&crop=faces&q=80",
    "fern_sweet":   "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=400&h=400&fit=crop&crop=faces&q=80",
    "namwan_22":    "https://images.unsplash.com/photo-1525134479668-1bee5c7c6845?w=400&h=400&fit=crop&crop=faces&q=80",
    "pim_pattaya":  "https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=400&h=400&fit=crop&crop=faces&q=80",
    "opal_nurse":   "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=400&h=400&fit=crop&crop=faces&q=80",
    "praew_model":  "https://images.unsplash.com/photo-1492106087820-71f1a00d2b11?w=400&h=400&fit=crop&crop=faces&q=80",
    "nuch_art":     "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400&h=400&fit=crop&crop=faces&q=80",
    "bow_bkk":      "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&h=400&fit=crop&crop=faces&q=80",
    "bam_fitness":  "https://images.unsplash.com/photo-1489424731084-a5d8b219a5bb?w=400&h=400&fit=crop&crop=faces&q=80",
    "ice_sweet23":  "https://images.unsplash.com/photo-1485217988980-11786ced9454?w=400&h=400&fit=crop&crop=faces&q=80",
    "kratae_thai":  "https://images.unsplash.com/photo-1557555187-23d685287bc3?w=400&h=400&fit=crop&crop=faces&q=80",
    "kevin_tw":     "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&h=400&fit=crop&crop=faces&q=80",
    "jason_taipei": "https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=400&h=400&fit=crop&crop=faces&q=80",
    "will_hsinchu": "https://images.unsplash.com/photo-1545167622-3a6ac756afa4?w=400&h=400&fit=crop&crop=faces&q=80",
    "eric_foodie":  "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&h=400&fit=crop&crop=faces&q=80",
    "david_travel": "https://images.unsplash.com/photo-1463453091185-61582044d556?w=400&h=400&fit=crop&crop=faces&q=80",
    "mark_gym":     "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400&h=400&fit=crop&crop=faces&q=80",
    "andy_design":  "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400&h=400&fit=crop&crop=faces&q=80",
    "chris_biz":    "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&h=400&fit=crop&crop=faces&q=80",
    "leo_music":    "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=400&h=400&fit=crop&crop=faces&q=80",
    "ryan_photo":   "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&h=400&fit=crop&crop=faces&q=80",
    "tom_doctor":   "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=400&h=400&fit=crop&crop=faces&q=80",
    "howard_fin":   "https://images.unsplash.com/photo-1610276198568-eb6d0ff53e48?w=400&h=400&fit=crop&crop=faces&q=80",
}

# Demo accounts that should display the gold ✓ verified badge.
DEMO_VERIFIED = {
    "kevin_tw", "jason_taipei", "will_hsinchu",
    "ploy_bkk", "mintra_cm", "fern_sweet", "kratae_thai", "praew_model",
}

# Old broken image URLs left over from before the Railway Volume was
# mounted — clear them so feed posts don't show 「圖片暫時無法載入」.
ORPHAN_POST_IMAGES = (
    "/uploads/post_00a896d4011f.png",
    "/uploads/post_1683736f19be.png",
    "/uploads/post_a0623bc633ec.jpg",
    "/uploads/post_8995e096adba.jpeg",
)


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
        # messages.* additions for reply / recall / media.
        "ALTER TABLE messages ALTER COLUMN content DROP NOT NULL",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS reply_to_id UUID REFERENCES messages(id) ON DELETE SET NULL",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_type VARCHAR(20) DEFAULT ''",
        # users.* additions for verification + privacy / notification / language settings.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_online BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_last_seen BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS allow_msg_from_non_premium BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_new_message BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_likes BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_gatherings BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS ui_language VARCHAR(10) DEFAULT 'zh-TW'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_translate_msgs BOOLEAN DEFAULT TRUE",
        # One-time cleanup — drop translation rows that were poisoned with
        # the legacy "[🇹🇼→🇹🇭] xxx" / "[🇹🇭→🇹🇼] xxx" fallback string. Those
        # weren't real translations; they were the failure-indicator that
        # leaked through. Future failures no longer get cached at all.
        "DELETE FROM message_translations WHERE translated_text LIKE '[%→%'",
    ]
    async with engine.begin() as conn:
        for stmt in statements:
            try:
                await conn.execute(text(stmt))
            except Exception as e:
                # Don't crash the app if a migration fails (e.g. column
                # already in the desired state on a fresh DB).
                print(f"[migration] skipped: {stmt.split()[2:6]} → {e}")


async def upgrade_demo_data():
    """Refresh the demo seed accounts with curated avatars + verified
    badges. Also clears 4 orphan post images that 404 because their
    files were lost in a pre-Volume Railway redeploy.

    Runs every startup but is idempotent (sets URLs that may already
    be set; user-uploaded avatars that don't match the demo URL set
    are left alone)."""
    async with engine.begin() as conn:
        # Update demo avatars (only ones that haven't been replaced by
        # a user-uploaded avatar — i.e. still pointing at randomuser.me).
        for username, url in DEMO_AVATARS.items():
            try:
                await conn.execute(text(
                    "UPDATE users SET avatar_url = :url "
                    "WHERE username = :u AND (avatar_url IS NULL OR avatar_url = '' "
                    "OR avatar_url LIKE '%randomuser.me%')"
                ), {"url": url, "u": username})
            except Exception as e:
                print(f"[avatar update] skipped {username}: {e}")

        # Mark a handful of demo accounts as verified
        if DEMO_VERIFIED:
            placeholders = ",".join(f":u{i}" for i in range(len(DEMO_VERIFIED)))
            params = {f"u{i}": u for i, u in enumerate(DEMO_VERIFIED)}
            try:
                await conn.execute(text(
                    f"UPDATE users SET is_verified = TRUE WHERE username IN ({placeholders})"
                ), params)
            except Exception as e:
                print(f"[verify] skipped: {e}")

        # Clear orphan post images so they don't render as broken
        for url in ORPHAN_POST_IMAGES:
            try:
                await conn.execute(text(
                    "UPDATE posts SET image_url = '' WHERE image_url = :u"
                ), {"u": url})
            except Exception as e:
                print(f"[orphan clear] skipped {url}: {e}")


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
    await upgrade_demo_data()
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

class _CachedStaticFiles(StaticFiles):
    """Same as StaticFiles but adds long-lived Cache-Control headers.
    Combined with the ?v=xxx cache-busting we already do on every CSS/JS
    link, this means returning visitors NEVER re-download static assets
    until we bump the version — eliminates a per-page 304 round trip.
    Uploads (user-generated images, avatars) get a shorter cache."""

    def __init__(self, *args, max_age: int = 31536000, immutable: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self._max_age = max_age
        self._immutable = immutable

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            cc = f"public, max-age={self._max_age}"
            if self._immutable:
                cc += ", immutable"
            response.headers["Cache-Control"] = cc
        return response


# Static JS/CSS — versioned by ?v=… so we can mark as immutable safely
app.mount("/static", _CachedStaticFiles(directory=static_dir), name="static")
# Uploads — user-generated, can be replaced on edit; cache 1 day, mutable
app.mount("/uploads", _CachedStaticFiles(directory=uploads_dir, max_age=86400, immutable=False), name="uploads")

templates = Jinja2Templates(directory=templates_dir)

# Include routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(posts.router)
app.include_router(messages.router)
app.include_router(albums.router)
app.include_router(subscriptions.router)
app.include_router(gatherings.router)
app.include_router(blocks.router)
app.include_router(notifications.router)
app.include_router(translate.router)
app.include_router(poll.router)


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
