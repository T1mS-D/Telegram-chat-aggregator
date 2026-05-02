import asyncio
import logging
from datetime import datetime, timezone

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

from app.config import VK_GROUP_TOKEN, VK_GROUP_ID, VK_ADMIN_ID
from app.db.database import AsyncSessionLocal
from app.db.crud import create_message, get_all_subscriptions
from app.services.ai_search import is_relevant, set_notifier
from app.services.embeddings import is_similar

logger = logging.getLogger(__name__)

LLM_ERROR_THRESHOLD = 3
_llm_error_count = 0


async def _notify_all_users_llm_down(vk):
    async with AsyncSessionLocal() as session:
        subs = await get_all_subscriptions(session)

    notified = set()
    for sub in subs:
        if sub.user_id in notified:
            continue
        notified.add(sub.user_id)
        try:
            vk.messages.send(
                user_id=sub.user_id,
                message=(
                    "⚠️ AI-сервис временно недоступен.\n"
                    "Сообщения продолжают сохраняться, "
                    "но уведомления по подпискам приостановлены до восстановления."
                ),
                random_id=0,
            )
        except Exception as e:
            logger.error(f"[NOTIFY_DOWN] user {sub.user_id}: {e}")


async def _process(vk, text: str, from_id: int, peer_id: int, link: str):
    global _llm_error_count

    if not text.strip():
        return

    date = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    async with AsyncSessionLocal() as session:
        await create_message(
            session,
            peer_id=peer_id,
            conversation_id=0,
            from_id=from_id,
            text=text,
            date=date,
        )
        subscriptions = await get_all_subscriptions(session)
        await session.commit()

    for sub in subscriptions:
        try:
            similar = is_similar(text, sub.prompt)
        except Exception as e:
            logger.error(f"[TFIDF] sub {sub.id} error: {e}")
            similar = False

        if not similar:
            logger.debug(f"[FILTER] sub {sub.id} rejected by TF-IDF")
            continue

        try:
            matched = await is_relevant(text, sub.prompt)
            _llm_error_count = 0
        except Exception as e:
            logger.error(f"[AI] sub {sub.id} error: {e}")
            _llm_error_count += 1
            if _llm_error_count == LLM_ERROR_THRESHOLD:
                logger.warning("[AI] LLM unavailable, notifying users...")
                await _notify_all_users_llm_down(vk)
            continue

        if matched:
            async with AsyncSessionLocal() as session:
                await session.commit()
            try:
                vk.messages.send(
                    user_id=sub.user_id,
                    message=(
                        f"🔔 Совпадение по запросу:\n"
                        f'"{sub.prompt}"\n\n'
                        f"📝 {text[:300]}\n\n"
                        f"🔗 {link}"
                    ),
                    random_id=0,
                )
                logger.info(f"[NOTIFY] user {sub.user_id} notified for sub {sub.id}")
            except Exception as e:
                logger.error(f"[VK] notify user {sub.user_id} failed: {e}")

    async with AsyncSessionLocal() as session:
        await session.commit()


def run_longpoll(loop: asyncio.AbstractEventLoop):
    vk_session = vk_api.VkApi(token=VK_GROUP_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, VK_GROUP_ID)

    set_notifier(vk, VK_ADMIN_ID)
    logger.info("[LONGPOLL] Started, listening for wall posts and comments...")

    for event in longpoll.listen():

        if event.type == VkBotEventType.WALL_POST_NEW:
            obj = event.object
            text = obj.get("text", "")
            from_id = obj.get("from_id", obj.get("created_by", 0))
            post_id = obj.get("id", 0)
            link = f"https://vk.com/wall-{VK_GROUP_ID}_{post_id}"
            logger.info(f"[WALL_POST] from={from_id}: {text[:60]}")

            future = asyncio.run_coroutine_threadsafe(
                _process(vk, text, from_id, -VK_GROUP_ID, link), loop
            )
            try:
                future.result(timeout=30)
            except Exception as e:
                logger.error(f"[LONGPOLL] wall post error: {e}")

        elif event.type == VkBotEventType.WALL_REPLY_NEW:
            obj = event.object
            text = obj.get("text", "")
            from_id = obj.get("from_id", 0)
            post_id = obj.get("post_id", 0)
            reply_id = obj.get("id", 0)
            link = f"https://vk.com/wall-{VK_GROUP_ID}_{post_id}?reply={reply_id}"
            logger.info(f"[WALL_COMMENT] from={from_id} on post {post_id}: {text[:60]}")

            future = asyncio.run_coroutine_threadsafe(
                _process(vk, text, from_id, -VK_GROUP_ID, link), loop
            )
            try:
                future.result(timeout=30)
            except Exception as e:
                logger.error(f"[LONGPOLL] comment error: {e}")