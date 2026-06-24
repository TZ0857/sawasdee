import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/sawasdee")
# Railway sometimes gives postgres:// instead of postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

SYNC_DATABASE_URL = DATABASE_URL.replace("+asyncpg", "")

SECRET_KEY = os.getenv("SECRET_KEY", "sawasdee-super-secret-key-change-in-production")
ALGORITHM = "HS256"
# Shorter session: a stolen / accidentally shared token expires within a day
# instead of a week. Users who actually use the app re-auth silently because
# the login form remembers their email; only the password needs typing.
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

DEEPL_API_KEY = os.getenv("DEEPL_API_KEY", "")

# Dedicated back-office admin login (separate from member login). Credentials
# come from env so the password is not hard-coded in the repo; the defaults
# let the panel work out of the box and can be overridden in Railway.
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "ADMIN")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "800101")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@sawasdee.internal")

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
