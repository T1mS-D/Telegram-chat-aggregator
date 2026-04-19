import logging
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from app.db.database import AsyncSessionLocal
from app.db.crud import (
    get_or_create_user,
    get_user_state,
    set_user_state,
    create_subscription,
    get_subscriptions_by_user,
    get_subscription,
    delete_subscription,
)

logger = logging.getLogger(__name__)

def make_main_keyboard() -> str:
    kb = VkKeyboard(one_time=False)
    kb.add_button("📋 Мои подписки", color=VkKeyboardColor.PRIMARY)
    kb.add_button("➕ Подписаться", color=VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button("🗑 Удалить подписку", color=VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()


async def handle_message(vk, user_id: int, text: str):
    text_stripped = text.strip()
    text_lower = text_stripped.lower()

    async with AsyncSessionLocal() as session:
        await get_or_create_user(session, user_id)
        state = await get_user_state(session, user_id)
        await session.commit()

    if state == "subscribe":
        if not text_stripped:
            _send(vk, user_id, "Промпт не может быть пустым. Попробуй ещё раз.",
                  keyboard=make_main_keyboard())
            return
        async with AsyncSessionLocal() as session:
            await set_user_state(session, user_id, None)
            sub = await create_subscription(session, user_id, text_stripped)
            await session.commit()
        _send(vk, user_id,
              f"✅ Подписка #{sub.id} создана:\n{sub.prompt}\n\n"
              "Буду уведомлять тебя при совпадении на стене сообщества.",
              keyboard=make_main_keyboard())
        return

    if state == "delete":
        num = text_stripped.replace("#", "").strip()
        if not num.isdigit():
            _send(vk, user_id, "Введи номер подписки цифрой. Например: 3",
                  keyboard=make_main_keyboard())
            return
        sub_id = int(num)
        async with AsyncSessionLocal() as session:
            await set_user_state(session, user_id, None)
            sub = await get_subscription(session, sub_id, user_id)
            if not sub:
                await session.commit()
                _send(vk, user_id, f"Подписка #{sub_id} не найдена.",
                      keyboard=make_main_keyboard())
                return
            await delete_subscription(session, sub_id)
            await session.commit()
        _send(vk, user_id, f"🗑 Подписка #{sub_id} удалена.",
              keyboard=make_main_keyboard())
        return

    if text_lower in ("начать", "start", "привет", ""):
        _send(vk, user_id,
              "👋 Привет! Я агрегатор VK-сообщества.\n\n"
              "Используй кнопки ниже 👇",
              keyboard=make_main_keyboard())

    elif text_lower in ("📋 мои подписки", "список", "мои подписки"):
        async with AsyncSessionLocal() as session:
            subs = await get_subscriptions_by_user(session, user_id)
        if not subs:
            _send(vk, user_id, "У тебя пока нет подписок. Нажми «➕ Подписаться».",
                  keyboard=make_main_keyboard())
        else:
            lines = [f"#{s.id}: {s.prompt}" for s in subs]
            _send(vk, user_id, "📋 Твои подписки:\n\n" + "\n".join(lines),
                  keyboard=make_main_keyboard())

    elif text_lower in ("➕ подписаться", "подписаться"):
        async with AsyncSessionLocal() as session:
            await set_user_state(session, user_id, "subscribe")
            await session.commit()
        _send(vk, user_id,
              "Напиши тему для отслеживания.\n"
              "Например: жалобы клиентов, упоминание сроков, недовольство сервисом",
              keyboard=make_main_keyboard())

    elif text_lower in ("🗑 удалить подписку", "удалить подписку", "удалить"):
        async with AsyncSessionLocal() as session:
            subs = await get_subscriptions_by_user(session, user_id)
        if not subs:
            _send(vk, user_id, "Нет подписок для удаления.", keyboard=make_main_keyboard())
        else:
            lines = [f"#{s.id}: {s.prompt}" for s in subs]
            async with AsyncSessionLocal() as session:
                await set_user_state(session, user_id, "delete")
                await session.commit()
            _send(vk, user_id,
                  "Напиши номер подписки для удаления:\n\n" + "\n".join(lines),
                  keyboard=make_main_keyboard())

    else:
        _send(vk, user_id,
              "Используй кнопки для управления подписками 👇",
              keyboard=make_main_keyboard())


def _send(vk, user_id: int, message: str, keyboard: str = None):
    kwargs = dict(user_id=user_id, message=message, random_id=0)
    if keyboard:
        kwargs["keyboard"] = keyboard
    try:
        vk.messages.send(**kwargs)
    except Exception as e:
        logger.error(f"[VK] send to {user_id} failed: {e}")