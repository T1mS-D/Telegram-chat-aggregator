import logging
import httpx
from app.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_vk = None
_admin_id = None


def set_notifier(vk, admin_id: int):
    global _vk, _admin_id
    _vk = vk
    _admin_id = admin_id


def _notify_admin(message: str):
    if _vk and _admin_id:
        try:
            _vk.messages.send(user_id=_admin_id, message=message, random_id=0)
        except Exception as e:
            logger.error(f"[NOTIFY_ADMIN] failed: {e}")


async def is_relevant(message_text: str, user_prompt: str) -> bool:
    system = (
        "Ты — интеллектуальный фильтр сообщений из VK-сообщества. "
        "Определи, соответствует ли сообщение критерию пользователя. "
        "Критерий может описывать жалобы, недовольства, конфликты, "
        "упоминания сроков, обязательств или любую другую тему. "
        "Отвечай строго одним словом: ДА или НЕТ."
    )
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Критерий: {user_prompt}\n\nСообщение: {message_text}"},
        ],
        "max_tokens": 5,
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(OPENROUTER_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip().upper()
        return answer.startswith("ДА")

    except httpx.TimeoutException:
        msg = "⚠️ LLM недоступен: превышено время ожидания (timeout). Проверь OpenRouter."
        logger.error(f"[AI] timeout")
        _notify_admin(msg)
        return False

    except httpx.HTTPStatusError as e:
        msg = f"⚠️ LLM вернул ошибку {e.response.status_code}. Проверь API-ключ и модель в .env"
        logger.error(f"[AI] HTTP {e.response.status_code}: {e.response.text[:200]}")
        _notify_admin(msg)
        return False

    except Exception as e:
        msg = f"⚠️ LLM недоступен: {type(e).__name__}. Подробности в logs/app.log"
        logger.error(f"[AI] unexpected error: {e}")
        _notify_admin(msg)
        return False