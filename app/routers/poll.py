"""Combined background poll endpoint.

The frontend used to poll three separate endpoints once per ~1.5s:
  - /api/gatherings/requests/pending-count   (host badge)
  - /api/gatherings/requests/mine            (applicant approve/reject toast)
  - /api/notifications/unread-count          (bell badge)

This single endpoint returns all three in one round trip so we cut
3 fetches/sec → 1 fetch/sec, ~66% fewer network requests and DB connections.
The individual endpoints stay (drawer / settings / etc. still call them).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.models.gathering import (
    Gathering, GatheringRequest, GatheringRequestStatus,
)
from app.services.auth import get_current_user

router = APIRouter(prefix="/api", tags=["poll"])


@router.get("/poll")
async def combined_poll(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Pending requests addressed to me as a host (mirrors /pending-count exact pattern)
    my_hosted_ids_q = await db.execute(
        select(Gathering.id).where(Gathering.host_id == current_user.id)
    )
    my_hosted_ids = [row[0] for row in my_hosted_ids_q.all()]
    if my_hosted_ids:
        pending_q = await db.execute(
            select(GatheringRequest.id)
            .where(
                GatheringRequest.gathering_id.in_(my_hosted_ids),
                GatheringRequest.status == GatheringRequestStatus.pending,
            )
        )
        pending_count = len(pending_q.scalars().all())
    else:
        pending_count = 0

    # My own outgoing requests (applicant view) so the client can detect status flips
    mine_q = await db.execute(
        select(GatheringRequest)
        .where(GatheringRequest.applicant_id == current_user.id)
        .options(selectinload(GatheringRequest.gathering))
        .order_by(GatheringRequest.created_at.desc())
        .limit(20)
    )
    my_requests = [
        {
            "id": str(r.id),
            "status": r.status.value,
            "gathering": {
                "id": str(r.gathering.id),
                "title": r.gathering.title,
            },
        }
        for r in mine_q.scalars().all()
        if r.gathering is not None
    ]

    # Unread notifications
    notif_q = await db.execute(
        select(Notification.id).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    notif_unread = len(notif_q.scalars().all())

    return {
        "gathering_pending": pending_count,
        "my_requests": my_requests,
        "notif_unread": notif_unread,
    }
