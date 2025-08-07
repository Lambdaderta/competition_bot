# database/__init__.py
# --- ИМПОРТЫ и БАЗОВЫЕ НАСТРОЙКИ ---
import os
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
# from sqlalchemy.ext.declarative import declarative_base # <-- УДАЛИТЬ ЭТУ СТРОКУ
from sqlalchemy import text

# --- Настройка логирования для этого модуля ---
logger = logging.getLogger(__name__)

# --- ИМПОРТИРУЕМ МОДЕЛИ (и Base) ---
# Это КРИТИЧЕСКИ ВАЖНО, чтобы metadata знала о всех таблицах
# Делаем это как можно раньше
from . import models # <-- Импортируем models, включая models.Base

# --- Теперь используем Base из models ---
Base = models.Base # <-- Берем Base, определенный в models.py
# ------------------------------------

# --- ПЕРЕМЕННЫЕ уровня МОДУЛЯ, но БЕЗ РАННЕЙ ПРОВЕРКИ ---
# Эти переменные будут инициализированы позже, при первом вызове get_engine()
# или init_db(). Это позволяет избежать ошибок импорта.
_engine = None
_AsyncSessionLocal = None
DATABASE_URL = None # Будет установлен позже

# --- ФУНКЦИИ ДЛЯ ЛЕНИВОЙ ИНИЦИАЛИЗАЦИИ ---
def get_engine():
    """Ленивая инициализация движка SQLAlchemy."""
    global _engine, DATABASE_URL
    if _engine is None:
        # Получаем URL только когда это действительно нужно
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            # Бросаем ошибку только здесь, когда движок реально нужен
            raise ValueError("DATABASE_URL не установлен. Проверьте .env файл.")
        logger.info(f"Создание движка SQLAlchemy для URL: {DATABASE_URL}")
        _engine = create_async_engine(DATABASE_URL, echo=False)
    return _engine

def get_sessionmaker():
    """Ленивая инициализация фабрики сессий."""
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        engine = get_engine() # Убедимся, что движок создан
        _AsyncSessionLocal = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    return _AsyncSessionLocal

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С БД ---
# Функция для получения сессии БД
async def get_db():
    """Dependency для FastAPI или просто для получения сессии."""
    AsyncSessionLocal = get_sessionmaker()
    async with AsyncSessionLocal() as session:
        yield session

# --- ИЗМЕНЕНО: init_models теперь просто асинхронная функция ---
async def init_models():
    """Асинхронная инициализация таблиц."""
    logger.info("Начало database.init_models()")
    # --- Отладка: Проверим, что модели импортированы ---
    logger.info(f"Метаданные Base: {Base.metadata}") # <-- Теперь это models.Base
    table_names = list(Base.metadata.tables.keys())
    logger.info(f"Зарегистрированные таблицы в metadata: {table_names}")
    if 'users' not in table_names:
        logger.error("ТАБЛИЦА 'users' НЕ НАЙДЕНА в metadata! Проверьте models.py")
    # ----------------------------------------------------
    engine = get_engine() # Получаем (и создаем, если нужно) движок
    async with engine.connect() as conn:
        logger.info("Получено соединение с БД.")
        async with conn.begin():
            logger.info("Начата транзакция. Подготовка к созданию таблиц...")
            try:
                result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
                existing_tables_before = [row[0] for row in result.fetchall()]
                logger.info(f"Таблицы в БД ДО create_all: {existing_tables_before}")
            except Exception as e:
                logger.warning(f"Не удалось получить список таблиц ДО создания: {e}")
            logger.info("Вызов Base.metadata.create_all()...")
            await conn.run_sync(Base.metadata.create_all) # <-- Теперь это metadata с таблицами
            logger.info("Base.metadata.create_all() завершён.")
            try:
                result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
                existing_tables_after = [row[0] for row in result.fetchall()]
                logger.info(f"Таблицы в БД ПОСЛЕ create_all: {existing_tables_after}")
                if 'users' in existing_tables_after:
                    logger.info("Таблица 'users' успешно создана.")
                else:
                    logger.error("ТАБЛИЦА 'users' ПО-ПРЕЖНЕМУ ОТСУТСТВУЕТ ПОСЛЕ create_all!")
            except Exception as e:
                logger.warning(f"Не удалось получить список таблиц ПОСЛЕ создания: {e}")
    logger.info("Конец database.init_models()")

# --- ИЗМЕНЕНО: init_db теперь асинхронная ---
async def init_db():
    """
    Асинхронная инициализация базы данных.
    """
    logger.info("Начало database.init_db()")
    try:
        await init_models()
        logger.info("database.init_models() завершена.")
    except Exception as e:
        logger.error(f"Ошибка внутри database.init_db(): {e}", exc_info=True)
        raise
    logger.info("Конец database.init_db()")

# --- Синхронная обёртка для lifespan (если очень нужно) ---
def init_db_sync():
    """Синхронная обертка."""
    logger.info("Начало database.init_db_sync()")
    import asyncio
    try:
        try:
            loop = asyncio.get_running_loop()
            logger.warning("init_db_sync вызвана внутри запущенного loop. Используйте await init_db() напрямую.")
            raise RuntimeError("Используйте await init_db() напрямую в асинхронном коде.")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("Запуск init_db в новом event loop...")
            loop.run_until_complete(init_db())
            logger.info("init_db завершена в новом loop.")
    except Exception as e:
        logger.error(f"Ошибка в init_db_sync: {e}", exc_info=True)
        raise
    logger.info("Конец database.init_db_sync()")