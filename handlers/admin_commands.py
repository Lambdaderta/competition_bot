# handlers/admin_commands.py
"""Глобальные админские команды, доступные в любом состоянии."""
import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from database import get_sessionmaker, crud
from sqlalchemy.ext.asyncio import AsyncSession

router = Router()
logger = logging.getLogger(__name__)

# --- Команда /add_admin ---
@router.message(Command("add_admin"))
async def cmd_add_admin(message: Message):
    """
    Команда для добавления администратора в соревнование.
    Использование: /add_admin <название_соревнования> @username [@username2 ...]
    """
    logger.info(f"Received /add_admin command from user {message.from_user.id}")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply(
            "Использование: `/add_admin <название_соревнования> @username [@username2 ...]`\n"
            "Пример: `/add_admin МойТурнир @newadmin @anotheradmin`",
            parse_mode='Markdown'
        )
        return

    # Разбираем аргументы: первое слово - название, остальное - список юзернеймов
    parts = args[1].split()
    if len(parts) < 2:
         await message.reply(
            "После названия соревнования укажите хотя бы один @username админа."
        )
         return

    competition_name = parts[0]
    usernames_to_add = [u for u in parts[1:] if u.startswith('@')]

    if not usernames_to_add:
        await message.reply("Не указаны корректные @username для добавления.")
        return

    AsyncSessionLocal = get_sessionmaker()
    async with AsyncSessionLocal() as db:
        try:
            # 1. Найти соревнование по названию
            competition = await crud.get_competition_by_name(db, competition_name)
            if not competition:
                await message.reply(f"Соревнование с названием '{competition_name}' не найдено.")
                return

            # 2. Проверить, является ли отправитель админом этого соревнования
            sender_db_user = await crud.get_user_by_id(db, message.from_user.id)
            if not sender_db_user or not (
                sender_db_user.id == competition.creator_id
            ):
                await message.reply("Вы не являетесь администратором этого соревнования.")
                return

            # 3. Найти пользователей по юзернеймам и добавить их в админы
            errors = []
            added_admins = []
            admins_list = list(competition.admins or []) # <-- admins_list это питоновский список из JSON
            
            for username in usernames_to_add:
                clean_username = username.lstrip('@')
                if not clean_username:
                    errors.append(f"Некорректный юзернейм: {username}")
                    continue

                db_user = await crud.get_user_by_username(db, clean_username)
                if not db_user:
                    errors.append(f"Пользователь @{clean_username} не найден в системе бота.")
                    continue

                if db_user.id == competition.creator_id:
                    errors.append(f"Пользователь @{clean_username} уже является создателем соревнования.")
                    continue

                # --- ПРОБЛЕМА 1: СРАВНЕНИЕ INT С ЭЛЕМЕНТАМИ СПИСКА ---
                # Если admins_list содержит строки, это не сработает.
                # Но SQLAlchemy обычно десериализует JSON массив int корректно.
                # Давайте добавим логирование для отладки.
                logger.debug(f"Проверка админа: user_id={db_user.id}, admins_list={admins_list}, type(admins_list)={type(admins_list)}")
                if db_user.id in admins_list:
                    errors.append(f"Пользователь @{clean_username} уже является администратором.")
                    continue
                # ----------------------------------------------------

                admins_list.append(db_user.id) # <-- Добавление int
                added_admins.append(f"@{clean_username}")
                logger.debug(f"Пользователь {db_user.id} добавлен во временный список админов.")

            # 4. Обновить список админов в БД
            logger.debug(f"Итоговый список админов для сохранения: {admins_list}")
            if added_admins:
                competition.admins = admins_list # <-- Присваиваем список int
                logger.debug(f"competition.admins установлен в {competition.admins}")
                await db.commit() # <-- Сохраняем
                logger.debug("Commit выполнен успешно.")
                await db.refresh(competition) # <-- Обновляем объект
                logger.debug("Refresh выполнен успешно.")
                success_msg = f"✅ Администраторы {', '.join(added_admins)} успешно добавлены в соревнование '{competition.name}'."
                if errors:
                    success_msg += f"\n⚠️ Ошибки:\n" + "\n".join(errors)
                await message.reply(success_msg)
            elif errors:
                await message.reply("❌ Ошибки при добавлении администраторов:\n" + "\n".join(errors))
            else:
                await message.reply("Нечего добавлять. Все указанные пользователи уже являются админами или создателем.")

        except Exception as e:
            logger.error(f"Ошибка в /add_admin: {e}", exc_info=True)
            await message.reply(f"❌ Произошла внутренняя ошибка: {e}")


# --- Команда /top ---
@router.message(F.text.startswith("топ"))
async def cmd_top(message: Message):
    """
    Команда для отображения топа игроков соревнования.
    Использование: топ <название_соревнования> [N]
    Где N - количество игроков в топе (по умолчанию 30).
    """
    logger.info(f"Received топ command from user {message.from_user.id}")
    
    args = message.text.split(maxsplit=2) # Разбиваем на 3 части максимум
    if len(args) < 2:
        await message.reply(
            "Использование: `/top <название_соревнования> [N]`\n"
            "Где `N` - количество игроков (по умолчанию 30).\n"
            "Пример: `/top МойТурнир` или `/top МойТурнир 10`",
            parse_mode='Markdown'
        )
        return

    competition_name = args[1]
    top_n = 30
    if len(args) > 2:
        try:
            top_n = int(args[2])
            if top_n <= 0:
                raise ValueError("N должно быть положительным числом.")
        except ValueError:
            await message.reply("Пожалуйста, укажите корректное число игроков для топа.")
            return

    AsyncSessionLocal = get_sessionmaker()
    async with AsyncSessionLocal() as db:
        try:
            # 1. Найти соревнование по названию
            competition = await crud.get_competition_by_name(db, competition_name)
            if not competition:
                await message.reply(f"Соревнование с названием '{competition_name}' не найдено.")
                return

            # 2. Получить список игроков, отсортированных по MMR (убывание)
            players = await crud.get_competition_players(db, competition.id)
            
            # Ограничить количество
            players_to_show = players[:top_n] if top_n > 0 else players

            if not players_to_show:
                await message.reply(f"В соревновании '{competition.name}' пока нет игроков.")
                return

            sorted_ranks_config = sorted(
                competition.ranks or [], 
                key=lambda r: r.get('mmr_threshold', 0), 
                reverse=True
            )

            def get_rank_name(mmr: int) -> str:
                """Определяет название ранга по MMR."""
                for rank_config in sorted_ranks_config:
                    if mmr >= rank_config.get('mmr_threshold', 0):
                        return rank_config.get('name', 'Без ранга')
                return 'Без ранга'

            report_lines = [f"🏆 <b>Топ {len(players_to_show)} игроков</b> в соревновании '<i>{competition.name}</i>':"]
            for i, player in enumerate(players_to_show, start=1):
                user = player.user
                username = f"@{user.username}" if user.username else f"ID:{user.user_id}"
                mmr = player.mmr
                rank_name = get_rank_name(mmr)
                player_id = player.id 
                
                report_lines.append(f"{i}. {username}, MMR: {mmr}, Ранг: {rank_name}, ID: {player_id}")

            await message.reply("\n".join(report_lines), parse_mode='HTML')

        except Exception as e:
            logger.error(f"Ошибка в /top: {e}", exc_info=True)
            await message.reply(f"❌ Произошла внутренняя ошибка: {e}")
