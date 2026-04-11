from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import stripe

from app.database import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.config import STRIPE_SECRET_KEY, STRIPE_PRICE_ID, STRIPE_WEBHOOK_SECRET

router = APIRouter(prefix="/api/subscriptions", tags=["subscriptions"])

stripe.api_key = STRIPE_SECRET_KEY


@router.post("/create-checkout")
async def create_checkout_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Stripe not configured")

    try:
        # Create or get Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                metadata={"user_id": str(current_user.id)},
            )
            current_user.stripe_customer_id = customer.id
            db.add(current_user)
            await db.flush()

        session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            mode="subscription",
            success_url="https://sawasdee.up.railway.app/subscription?status=success",
            cancel_url="https://sawasdee.up.railway.app/subscription?status=cancel",
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")

        result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_subscribed = True
            user.stripe_subscription_id = subscription_id
            db.add(user)

    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")

        result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_subscribed = False
            user.stripe_subscription_id = ""
            db.add(user)

    return {"status": "ok"}


@router.get("/status")
async def subscription_status(current_user: User = Depends(get_current_user)):
    return {
        "is_subscribed": current_user.is_subscribed,
        "stripe_customer_id": current_user.stripe_customer_id or "",
    }
