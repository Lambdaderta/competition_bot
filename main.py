# main.py (ФИНАЛЬНАЯ ВЕРСИЯ ДЛЯ ИНИЦИАЛИЗАЦИИ БД)
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from handlers import match_handlers 
from handlers import reg_handler
from handlers import admin_commands

# --- Настройка логирования ДО ВСЕГО ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.info("--- ЗАПУСК БОТА ---")

logger.info("Импорт моделей...")
from database import models 

# --- Загрузка переменных окружения ---
env_path = Path(__file__).parent / ".env"
logger.info(f"Путь к .env файлу: {env_path}")
if env_path.exists():
    load_res = load_dotenv(dotenv_path=env_path)
    logger.info(f"Загрузка .env: {'Успешна' if load_res else 'Файл найден, но переменные могли не загрузиться'}")
else:
    logger.error(f"Файл .env НЕ НАЙДЕН по пути: {env_path}")

# --- Проверка DATABASE_URL ---
DATABASE_URL = os.getenv("DATABASE_URL")
logger.info(f"Значение DATABASE_URL из .env: {DATABASE_URL}")
if not DATABASE_URL:
    logger.critical("DATABASE_URL не установлен! Выход.")
    raise ValueError("DATABASE_URL не найден в .env файле или переменных окружения.")

# --- Конфигурация ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
logger.info(f"Значение BOT_TOKEN из .env: {'Установлен' if BOT_TOKEN else 'НЕ УСТАНОВЛЕН'}")
if not BOT_TOKEN:
    logger.critical("BOT_TOKEN не установлен! Выход.")
    raise ValueError("BOT_TOKEN не найден в .env файле или переменных окружения.")


from handlers import base_handlers, org_handlers, player_handlers

from database import init_db 


async def set_commands(bot: Bot):
    commands = [
        types.BotCommand(command="start", description="Основная команда. Нажимайте"),
        types.BotCommand(command="help", description="Помощь"),
        types.BotCommand(command="add_admin", description="Добавить админа в соревнование, подробнее в help")
    ]
    await bot.set_my_commands(commands)


@asynccontextmanager
async def lifespan(dp: Dispatcher):
    yield

async def main():
    
    try:
        await init_db() # <-- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: await
    except Exception as e:
        raise
    # -------------------------------------

    logger.info("Создание хранилища состояний...")
    storage = MemoryStorage()

    dp = Dispatcher(storage=storage, lifespan=lifespan)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp.include_router(base_handlers.router)
    dp.include_router(org_handlers.router)
    dp.include_router(match_handlers.router)
    dp.include_router(reg_handler.router) 
    dp.include_router(admin_commands.router)
    dp.include_router(player_handlers.router)


    try:
        await set_commands(bot)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем (KeyboardInterrupt/SystemExit).")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске поллинга: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    logger.info("=== ВХОД В main() через asyncio.run ===")
    try:
        asyncio.run(main()) # <-- Это запускает event loop и main()
    except Exception as e:
        logger.error(f"Критическая ошибка в asyncio.run(main()): {e}", exc_info=True)
    logger.info("=== ВЫХОД ИЗ main() ===")
