import logging
from aiogram import Router, F
from aiogram.types import Message
from database import get_sessionmaker, crud
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text.startswith("/рег"))
async def register_user(message: Message):
    """
    Регистрирует пользователя в системе бота.
    Использование: /рег
    """
    try:
        AsyncSessionLocal = get_sessionmaker()
        async with AsyncSessionLocal() as db:
            telegram_user_id = message.from_user.id
            username = message.from_user.username or ""
            full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            
            db_user = await crud.get_or_create_user(db, telegram_user_id, username, full_name)
            
            if db_user:
                response_text = (
                    f"✅ Вы зарегистрированы в системе, {db_user.full_name}!\n"
                    f"Ваш Telegram ID: <code>{db_user.user_id}</code>\n"
                )
                if db_user.username:
                    response_text += f"Ваш тег: @{db_user.username}\n"
                else:
                    response_text += "У вас нет тега. Рекомендуется его установить в настройках Telegram для удобства админов.\n"
                
                response_text += f"Ваш внутренний ID в боте: <code>{db_user.id}</code>"
            else:
                response_text = "❌ Произошла ошибка при регистрации. Пожалуйста, попробуйте позже."

            await message.reply(response_text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка при регистрации пользователя {message.from_user.id}: {e}", exc_info=True)
        await message.reply(
            f"❌ Произошла внутренняя ошибка при регистрации: {str(e)}\n"
            f"Пожалуйста, попробуйте позже или обратитесь к администратору."
        )

# Алиас для английской команды
@router.message(F.text.startswith("/reg"))
async def register_user_en(message: Message):
    """Английская версия команды регистрации."""
    await register_user(message)
