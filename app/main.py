import asyncio
import logging
import logging.handlers
import threading
import os

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType

from app.config import VK_GROUP_TOKEN, VK_GROUP_ID
from app.handlers.user_handlers import handle_message
from app.services.vk_listener import run_longpoll


def setup_logging():
    os.makedirs("logs", exist_ok=True)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    file_handler = logging.handlers.RotatingFileHandler(
        "logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console)
    root.addHandler(file_handler)


logger = logging.getLogger(__name__)


def run_dm_listener(loop: asyncio.AbstractEventLoop):
    vk_session = vk_api.VkApi(token=VK_GROUP_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, VK_GROUP_ID)

    logger.info("[DM] Listening for direct messages...")

    for event in longpoll.listen():
        if event.type != VkBotEventType.MESSAGE_NEW:
            continue

        obj = event.object.message
        peer_id = obj.get("peer_id", 0)
        from_id = obj.get("from_id", 0)
        text = obj.get("text", "")

        if peer_id != from_id or from_id <= 0:
            continue

        logger.info(f"[DM] from={from_id}: {text[:60]}")

        future = asyncio.run_coroutine_threadsafe(
            handle_message(vk, from_id, text), loop
        )
        try:
            future.result(timeout=30)
        except Exception as e:
            logger.error(f"[DM] handler error: {e}")


async def main():
    setup_logging()
    loop = asyncio.get_running_loop()

    t1 = threading.Thread(target=run_longpoll, args=(loop,), daemon=True)
    t2 = threading.Thread(target=run_dm_listener, args=(loop,), daemon=True)

    t1.start()
    t2.start()

    logger.info("[MAIN] Both listeners running. Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())