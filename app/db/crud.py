from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.db.models import User, Subscription, Message

async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    user = await session.get(User, user_id)
    if not user:
        user = User(id=user_id, first_name=first_name, last_name=last_name)
        session.add(user)
        await session.flush()
    return user


async def get_user_state(session: AsyncSession, user_id: int) -> str | None:
    user = await session.get(User, user_id)
    return user.state if user else None

async def set_user_state(session: AsyncSession, user_id: int, state: str | None) -> None:
    user = await session.get(User, user_id)
    if user:
        user.state = state

async def create_subscription(session: AsyncSession, user_id: int, prompt: str) -> Subscription:
    sub = Subscription(user_id=user_id, prompt=prompt)
    session.add(sub)
    await session.flush()
    await session.refresh(sub)
    return sub


async def get_subscriptions_by_user(session: AsyncSession, user_id: int) -> list[Subscription]:
    result = await session.execute(
        select(Subscription).where(Subscription.user_id == user_id)
    )
    return result.scalars().all()


async def get_subscription(session: AsyncSession, sub_id: int, user_id: int) -> Subscription | None:
    result = await session.execute(
        select(Subscription).where(
            Subscription.id == sub_id,
            Subscription.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_subscription(session: AsyncSession, sub_id: int) -> None:
    await session.execute(delete(Subscription).where(Subscription.id == sub_id))


async def get_all_subscriptions(session: AsyncSession) -> list[Subscription]:
    result = await session.execute(select(Subscription))
    return result.scalars().all()

async def create_message(
    session: AsyncSession,
    peer_id: int,
    conversation_id: int,
    from_id: int | None,
    text: str,
    date: datetime,
) -> Message:
    msg = Message(
        peer_id=peer_id,
        conversation_id=conversation_id,
        from_id=from_id,
        text=text,
        date=date,
    )
    session.add(msg)
    await session.flush()
    return msg