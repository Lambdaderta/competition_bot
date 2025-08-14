import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, func, and_
from database import get_sessionmaker, crud
from database import models 
from aiogram.filters import Command

router = Router()
logger = logging.getLogger(__name__)


import math


from keyboards.player_keyboards import (
    get_player_main_menu,
    get_player_competitions_keyboard
)


ITEMS_PER_PAGE = 10

router = Router()

@router.callback_query(F.data == "role_participant")
async def enter_participant_menu(callback: CallbackQuery):
    """Обработчик нажатия кнопки 'Участник'."""
    await callback.message.edit_text(
        "Меню игрока",
        reply_markup=get_player_main_menu() 
    )
    await callback.answer()


@router.callback_query(F.data == 'my_played_competitions')
async def show_player_competitions(callback: CallbackQuery):
    await show_player_competitions_page(callback, page=1)


async def show_player_competitions_page(callback: CallbackQuery, page: int):
    """Вспомогательная функция для отображения конкретной страницы."""
    AsyncSessionLocal = get_sessionmaker()
    async with AsyncSessionLocal() as db:
        try:
            # Получаем внутренний ID пользователя
            db_user = await crud.get_user_by_id(db, callback.from_user.id)
            if not db_user:
                 await callback.message.edit_text("Ошибка: Вы не зарегистрированы в системе.")
                 await callback.answer()
                 return

            internal_user_id = db_user.id

            all_competitions = await crud.get_played_competitions(db, internal_user_id)
            
            if not all_competitions:
                await callback.message.edit_text(
                    "Вы не участвуете ни в одном соревновании",
                    reply_markup=get_player_main_menu() 
                )
                await callback.answer()
                return

            total_items = len(all_competitions)
            total_pages = math.ceil(total_items / ITEMS_PER_PAGE) or 1

            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages

            start_index = (page - 1) * ITEMS_PER_PAGE
            end_index = start_index + ITEMS_PER_PAGE
            competitions_on_page = all_competitions[start_index:end_index]

            if total_pages > 1:
                header = f"<b>Мои соревнования</b> (Страница {page}/{total_pages}):\n\n"
            else:
                header = "<b>Мои соревнования:</b>\n\n"
            
            if competitions_on_page:
                comp_lines = []
                for comp in competitions_on_page:
                    comp_lines.append(f"• <b>{comp.name}</b> (ID: {comp.id})")
                body = "\n".join(comp_lines)
            else:
                body = "На этой странице соревнований нет."

            message_text = header + body

            await callback.message.edit_text(
                message_text,
                reply_markup=get_player_competitions_keyboard(competitions_on_page, page, total_pages, ITEMS_PER_PAGE)
            )
            await callback.answer()

        except Exception as e:
            await callback.message.edit_text(
                f"❌ Произошла ошибка: {e}",
                reply_markup=get_player_main_menu()
            )
            await callback.answer()


@router.callback_query(F.data.startswith("player_comps_page_"))
async def navigate_my_competitions(callback: CallbackQuery):
    """Обрабатывает нажатие кнопок навигации по страницам 'Мои соревнования'."""
    try:
        page_num = int(callback.data.split("_")[-1])
        await show_player_competitions_page(callback, page=page_num)
    except (ValueError, IndexError):
        await callback.answer("Ошибка навигации.", show_alert=True)



@router.callback_query(F.data.startswith("view_comp_"))
async def show_compet_stats(callback: CallbackQuery):
    try:
        compet_id = int(callback.data.split("_")[-1])
        await show_player_stats(callback, compet_id)
    except (ValueError, IndexError):
        await callback.answer("Ошибка.", show_alert=True)


async def show_player_stats(callback, compet_id, flag = False): # Предполагается, что compet_id - это внутренний ID соревнования
    """
    Показывает статистику игрока в конкретном соревновании.
    """
    AsyncSessionLocal = get_sessionmaker()
    async with AsyncSessionLocal() as db:
        try:
            # 1. Получаем или создаем запись игрока
            # Предполагается, что callback.from_user.id - это Telegram ID
            db_user = await crud.get_user_by_id(db, callback.from_user.id)
            if not db_user:
                await callback.message.edit_text(
                    "❌ Ошибка: Вы не зарегистрированы в системе бота. "
                    "Пожалуйста, сначала взаимодействуйте с ботом в личных сообщениях.",
                    reply_markup=get_player_main_menu() # Убедитесь, что эта функция/клавиатура существует
                )
                await callback.answer()
                return

            internal_user_id = db_user.id

            # get_or_create_player требует competition_id и user_id
            player = await crud.get_or_create_player(db, competition_id=compet_id, user_id=internal_user_id)
            
            # 2. Получаем объект соревнования для доступа к ranks и achievements
            competition = await crud.get_competition_by_id(db, compet_id)
            if not competition:
                 # Очень маловероятно, если player существует
                 await callback.message.edit_text("❌ Ошибка: Соревнование не найдено.")
                 await callback.answer()
                 return

            # 3. Определяем ранг игрока
            player_rank_name = "Без ранга"
            if competition.ranks:
                # Сортируем ранги по убыванию порога MMR, чтобы найти первый подходящий
                sorted_ranks = sorted(
                    competition.ranks,
                    key=lambda r: r.get('mmr_threshold', 0),
                    reverse=True
                )
                for rank_config in sorted_ranks:
                    if player.mmr >= rank_config.get('mmr_threshold', 0):
                        player_rank_name = rank_config.get('name', 'Без ранга')
                        break

            # 4. Рассчитываем место в топе
            # Используем SQL-подобный запрос: считаем, сколько игроков имеют MMR строго больше
            result = await db.execute(
                select(func.count(models.Player.id))
                .where(
                    models.Player.competition_id == compet_id,
                    models.Player.mmr > player.mmr # Игроки с MMR строго больше
                )
            )
            # Место = количество игроков с большим MMR + 1
            place_in_top = result.scalar() + 1

            # 5. Рассчитываем процент побед и общее количество матчей
            # Получаем все участия текущего пользователя в матчах этого соревнования
            # Нужно JOIN MatchParticipant с Match по match_id, фильтруя по competition_id и user_id

            # Подзапрос: все матчи в этом соревновании
            matches_subq = select(models.Match.id).where(models.Match.competition_id == compet_id).subquery()
            
            # Основной запрос: считаем MatchParticipant
            total_matches_stmt = select(func.count(models.MatchParticipant.id)).where(
                and_(
                    models.MatchParticipant.user_id == internal_user_id,
                    models.MatchParticipant.match_id.in_(select(matches_subq.c.id)) # Участвовал в матче этого соревнования
                )
            )
            wins_stmt = select(func.count(models.MatchParticipant.id)).where(
                and_(
                    models.MatchParticipant.user_id == internal_user_id,
                    models.MatchParticipant.is_winner.is_(True), # Победитель
                    models.MatchParticipant.match_id.in_(select(matches_subq.c.id))
                )
            )

            total_matches_result = await db.execute(total_matches_stmt)
            wins_result = await db.execute(wins_stmt)

            total_matches = total_matches_result.scalar()
            wins_count = wins_result.scalar()

            win_percentage = 0
            if total_matches > 0:
                win_percentage = round((wins_count / total_matches) * 100, 2)

            # 6. Формируем список достижений
            achievements_lines = ["<b>Достижения:</b>"]
            if player.achievements:
                # Сортируем по названию или количеству для консистентности
                for ach_name, count in sorted(player.achievements.items()):
                    achievements_lines.append(f" • {ach_name}: {count}")
            else:
                achievements_lines.append(" • Нет достижений")

            # 7. Формируем итоговое сообщение
            stats_text = (
                f"📊 <b>Ваша статистика в соревновании '{competition.name}':</b>\n\n"
                f"<b>MMR:</b> {player.mmr}\n"
                f"<b>Ранг:</b> {player_rank_name}\n"
                f"<b>Место в топе:</b> {place_in_top}\n\n"
                f"<b>Всего матчей:</b> {total_matches}\n"
                f"<b>Побед:</b> {wins_count}\n"
                f"<b>Процент побед:</b> {win_percentage}%\n"
                f"<b>Текущая серия:</b> {player.streak}\n\n"
                f"{'\n'.join(achievements_lines)}"
            )

            if flag:
                await callback.message.edit_text(
                stats_text,
                parse_mode='HTML', 
                )
                await callback.answer()

            else:
                await callback.message.edit_text(
                stats_text,
                parse_mode='HTML', 
                reply_markup=get_player_main_menu() 
            )
                await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка в show_player_stats для пользователя {callback.from_user.id}, соревнования {compet_id}: {e}", exc_info=True)
            await callback.message.edit_text(
                f"❌ Произошла ошибка при получении статистики: {e}. Напишите организаторам.",
                reply_markup=get_player_main_menu() # Убедитесь, что клавиатура определена
            )
            await callback.answer()


################################


@router.message(F.text.startswith('стат')) # Или любое другое название, например, Command("stats"), Command("profile")
async def cmd_player_stats_in_chat(message: Message):
    logger.info(f"Получена команда /ммр от пользователя {message.from_user.id} в чате {message.chat.id}")

    args = message.text.split(maxsplit=1) 
    competition_name = None
    if len(args) > 1:
        competition_name = args[1].strip() 

    # 2. Если имя не указано, можно попробовать получить единственное соревнование в чате
    # или запросить уточнение. Для простоты будем требовать имя.
    if not competition_name:
        await message.reply(
            "Пожалуйста, укажите название соревнования.\n"
            "Использование: `стат <название_соревнования>`",
            parse_mode='Markdown'
        )
        return

    # 3. Получаем сессию БД
    AsyncSessionLocal = get_sessionmaker()
    async with AsyncSessionLocal() as db:
        try:
            # 4. Находим соревнование по названию и ID чата
            competition = await crud.get_competition_by_name(db, competition_name)
            if not competition:
                await message.reply(f"❌ Соревнование с названием '{competition_name}' не найдено.")
                return

            # 5. Проверяем, что соревнование привязано к *этому* чату
            if competition.chat_id != message.chat.id:
                await message.reply(
                    f"❌ Соревнование '{competition_name}' не привязано к этому чату (ID: {message.chat.id})."
                )
                return

            # 6. Получаем внутренний ID пользователя в БД
            db_user = await crud.get_user_by_id(db, message.from_user.id)
            if not db_user:
                # Создаем пользователя, если его нет (опционально, или просто сообщаем об ошибке)
                # full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                # db_user = await crud.get_or_create_user(db, message.from_user.id, message.from_user.username or "", full_name)
                await message.reply(
                    "❌ Вы не зарегистрированы в системе бота. "
                    "Пожалуйста, сначала напишите боту в личные сообщения."
                )
                return

            # 7. Проверяем, участвует ли пользователь в соревновании
            player = await crud.get_or_create_player(db, competition.id, db_user.id)
            if not player:
                 # Регистрируем автоматически или сообщаем об ошибке
                 # player = await crud.get_or_create_player(db, competition.id, db_user.id, competition.start_mmr)
                 await message.reply(
                     f"❌ Вы не участвуете в соревновании '{competition.name}'."
                 )
                 return

            # 8. --- КЛЮЧЕВОЙ МОМЕНТ ---
            # Создаем "импровизированный" объект callback, который будет совместим
            # с вашей функцией show_player_stats.
            # Это не настоящий CallbackQuery, но мы можем создать "утиный тип" (duck typing).
            # Главное, чтобы объект имел нужные атрибуты: message, from_user, answer().
            
            class MockCallback:
                def __init__(self, real_message, real_user):
                    self.message = real_message
                    self.from_user = real_user
                    self._answered = False
                    self.flag = True

                async def answer(self):
                    if not self._answered:
                        logger.debug("MockCallback.answer() вызван")
                        self._answered = True


            class MockEditableMessage:
                 def __init__(self, original_message):
                     self.original_message = original_message

                 async def edit_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
                     await self.original_message.reply(
                         text=text,
                         parse_mode=parse_mode,
                         reply_markup=reply_markup,
                         **kwargs
                     )

            mock_message = MockEditableMessage(message)
            mock_callback = MockCallback(mock_message, message.from_user)

            # 9. Вызываем вашу существующую функцию show_player_stats
            # Передаем ей импровизированный callback и ID соревнования
            await show_player_stats(mock_callback, competition.id, flag=True) 

            # Примечание: show_player_stats должна уметь обрабатывать ошибки внутри себя
            # и отправлять сообщения через mock_callback.message.edit_text (который теперь reply).

        except Exception as e:
            logger.error(f"Ошибка в cmd_player_stats_in_chat для пользователя {message.from_user.id}, чата {message.chat.id}, соревнования '{competition_name}': {e}", exc_info=True)
            await message.reply(f"❌ Произошла ошибка при получении статистики: {e}")