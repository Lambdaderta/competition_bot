# handlers/match_handlers.py
"""
Хендлеры для управления матчами/исходами в чатах соревнований.
"""
import logging
import re
from typing import List, Tuple, Optional, Dict, Any

from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

from database import get_sessionmaker, crud
from sqlalchemy.ext.asyncio import AsyncSession
from utils.mmr_calculator import (
    calculate_mmr_change_by_formula,
    calculate_mmr_change_by_ranges
)

router = Router()
logger = logging.getLogger(__name__)


async def is_user_admin_in_chat(bot, chat_id: int, user_id: int) -> bool:
    """
    Проверяет, является ли пользователь администратором в указанном чате.
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except TelegramAPIError as e:
        logger.error(f"Ошибка при проверке админки пользователя {user_id} в чате {chat_id}: {e}")
        return False

async def ensure_player_registered(db: AsyncSession, competition_id: int, user_id: int, start_mmr: int = 0):
    """
    Гарантирует, что пользователь зарегистрирован как участник соревнования (Player).
    Если нет - создает запись.
    """
    player = await crud.get_player_by_competition_and_user(db, competition_id, user_id)
    if not player:
        # Создаем нового участника с стартовым MMR из соревнования или переданным
        player = await crud.get_or_create_player(db, competition_id, user_id, start_mmr)
        logger.info(f"Пользователь ID {user_id} автоматически зарегистрирован в соревновании ID {competition_id} как Player ID {player.id}")
    return player

def parse_match_command(text: str) -> Tuple[str, List[Tuple[str, List[str]]], str]:
    """
    Парсит команду /Исход.

    Ожидаемый формат:
    /Исход НазваниеСоревнования @user1: ach1, ach2, @user2: ach3, @winner

    Возвращает:
        Tuple[
            str,                         # Название соревнования
            List[Tuple[str, List[str]]], # Список (юзернейм, [достижения])
            str                          # Юзернейм победителя
        ]
    """
    # Убираем команду и возможные пробелы в начале
    command_part = "/Исход"
    if text.lower().startswith(command_part.lower()):
        payload = text[len(command_part):].strip()
    else:
        # Если команда как-то иначе пришла
        payload = text.strip()

    if not payload:
        raise ValueError("После команды /Исход ничего не указано.")

    # Разделяем по запятым, но учитываем, что внутри ": ..." тоже могут быть запятые
    # Лучше разделить по последней запятой - всё после неё это победитель
    parts = [p.strip() for p in payload.split(',')]
    if len(parts) < 2: # Нужно хотя бы название соревнования + победитель
        raise ValueError("Неверный формат. Нужно указать название соревнования, участников и победителя.")

    # Последний элемент - победитель
    winner_part = parts[-1]
    winner_username = winner_part.strip()
    if not winner_username.startswith('@'):
         raise ValueError("Победитель должен быть указан как @username.")

    # Остальные элементы - это название соревнования и участники
    pre_winner_parts = parts[:-1]
    if not pre_winner_parts:
        raise ValueError("Не указано название соревнования или участники.")

    # Первый элемент до запятой - это потенциально "НазваниеСоревнования @user1: ach1"
    # Нам нужно отделить название соревнования от первого участника.
    first_part = pre_winner_parts[0]
    if ':' in first_part:
        # Значит, первый участник указан в этом же куске
        # Например: "Турнир @user1: ach1"
        space_idx = first_part.find(' ')
        if space_idx == -1:
            raise ValueError("Неверный формат первого элемента. Укажите название соревнования.")
        
        competition_name = first_part[:space_idx].strip()
        if not competition_name:
             raise ValueError("Не указано название соревнования.")

        first_participant_part = first_part[space_idx+1:].strip()
        if not first_participant_part:
             raise ValueError("Не указан первый участник после названия соревнования.")

        # Остальные участники
        participant_parts = [first_participant_part] + pre_winner_parts[1:]
    else:
        # Значит, первый элемент - это только название соревнования
        # Например: "Турнир"
        competition_name = first_part.strip()
        if not competition_name:
             raise ValueError("Не указано название соревнования.")
        participant_parts = pre_winner_parts[1:] # Остальные элементы - участники

    if not participant_parts:
        raise ValueError("Не указаны участники (кроме победителя).")

    participants_data = []
    for part in participant_parts:
        if ':' in part:
            username_part, ach_part = part.split(':', 1)
            username = username_part.strip()
            if not username.startswith('@'):
                 raise ValueError(f"Неверный формат участника: {part}. Юзернейм должен начинаться с @.")
            achievements_raw = ach_part.strip()
            if achievements_raw:
                # Разделяем достижения по запятым и очищаем
                achievements = [a.strip() for a in achievements_raw.split(',') if a.strip()]
            else:
                achievements = []
        else:
            # Нет достижений, только юзернейм
            username = part.strip()
            if not username.startswith('@'):
                 raise ValueError(f"Неверный формат участника: {part}. Юзернейм должен начинаться с @.")
            achievements = []
        
        participants_data.append((username, achievements))
    
    # Добавляем победителя в список участников, если его там нет
    winner_in_participants = any(p[0].lower() == winner_username.lower() for p in participants_data)
    if not winner_in_participants:
        participants_data.append((winner_username, [])) # У победителя пока нет доп. достижений от админа

    return competition_name, participants_data, winner_username

# --- Основной хендлер ---

@router.message(F.text.lower().startswith("/исход"), F.chat.type.in_({"group", "supergroup"}))
async def handle_match_outcome(message: Message, bot):
    """
    Обрабатывает команду /Исход в чате соревнования.
    Формат: /Исход НазваниеСоревнования, @user1: ach1, ach2, @user2: ach3, @winner
    """
    logger.info(f"Получена команда /Исход от пользователя {message.from_user.id} в чате {message.chat.id}")

    # 1. Парсинг команды
    try:
        competition_name, participants_data, winner_username = parse_match_command(message.text)
        logger.debug(f"Распарсенные данные: соревнование={competition_name}, участники={participants_data}, победитель={winner_username}")
    except ValueError as e:
        await message.reply(f"❌ Ошибка в формате команды: {e}\nИспользуйте: `/Исход НазваниеСоревнования @user1: ach1, ach2, @user2: ach3, @winner`", parse_mode='Markdown')
        return

    # Используем асинхронный контекстный менеджер для сессии
    AsyncSessionLocal = get_sessionmaker()
    async with AsyncSessionLocal() as db:
        try:
            # 2. Проверка, есть ли соревнование с таким названием в этом чате
            competition = await crud.get_competition_by_name(db, competition_name)
            if not competition:
                await message.reply(
                    f"❌ Соревнование с названием '{competition_name}' не найдено.",
                    disable_notification=True
                )
                return

            if competition.chat_id != message.chat.id:
                 await message.reply(
                     f"❌ Соревнование '{competition_name}' не привязано к этому чату (ID: {message.chat.id}).",
                     disable_notification=True
                 )
                 return

            # 3. Проверка, является ли отправитель админом соревнования или бота в чате
            sender_telegram_id = message.from_user.id
            sender_db_user = await crud.get_user_by_id(db, sender_telegram_id)

            if not sender_db_user:
                 # Создаем отправителя в БД, если его там нет
                 sender_full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                 sender_db_user = await crud.get_or_create_user(db, sender_telegram_id, message.from_user.username or "", sender_full_name)
                 logger.info(f"Пользователь {sender_telegram_id} автоматически создан в БД.")

            sender_is_competition_admin = (
                sender_db_user.id == competition.creator_id or
                sender_db_user.id in competition.admins
            )
            sender_is_chat_admin = await is_user_admin_in_chat(bot, message.chat.id, sender_telegram_id)

            if not (sender_is_competition_admin or sender_is_chat_admin):
                await message.reply(
                    "❌ Вы не являетесь администратором этого соревнования или чата.",
                    disable_notification=True
                )
                return

            # 4. Сбор и обработка данных об участниках
            # Сначала соберем все уникальные юзернеймы
            all_usernames = {username for username, _ in participants_data}
            all_usernames.add(winner_username) # Убедимся, что победитель тоже учтен

            # Создадим словарь для хранения внутренних ID пользователей
            user_internal_ids = {} # username -> internal_id
            errors = []

            for username in all_usernames:
                if not username.startswith('@'):
                    errors.append(f"Неверный формат юзернейма: {username}")
                    continue

                clean_username = username.lstrip('@')
                if not clean_username:
                    errors.append(f"Пустой юзернейм: {username}")
                    continue

                # Пытаемся найти пользователя в БД
                db_user = await crud.get_user_by_username(db, clean_username)
                
                if db_user:
                    # Пользователь найден в БД
                    user_internal_ids[username] = db_user.id
                else:
                    # Пользователь не найден в БД, пытаемся получить его из чата
                    try: # Это не будет работать, нейронка бреда написала, но ошибки он все равно выдаст так что пофик
                        # Получаем информацию о пользователе из чата
                        chat_member = await bot.get_chat_member(message.chat.id, clean_username)
                        chat_user = chat_member.user
                        
                        # Создаем пользователя в БД
                        full_name = f"{chat_user.first_name or ''} {chat_user.last_name or ''}".strip()
                        new_db_user = await crud.get_or_create_user(db, chat_user.id, chat_user.username or "", full_name)
                        user_internal_ids[username] = new_db_user.id
                        logger.info(f"Пользователь {username} (ID: {chat_user.id}) автоматически добавлен в БД.")
                        
                    except TelegramAPIError as e:
                        # Не удалось получить пользователя из чата
                        logger.warning(f"Не удалось получить пользователя {username} из чата {message.chat.id}: {e}")
                        errors.append(f"Пользователь {username} не найден в чате или не может быть добавлен.")
                    except Exception as e:
                        logger.error(f"Ошибка при добавлении пользователя {username} в БД: {e}")
                        errors.append(f"Ошибка при обработке пользователя {username}.")

            if errors:
                error_msg = "\n".join(errors)
                await message.reply(f"❌ Ошибки при обработке участников:\n{error_msg}", disable_notification=True)
                return

            # 5. Регистрация участников в соревновании (если нужно)
            player_objs_map = {} # internal_user_id -> models.Player obj
            for username, internal_id in user_internal_ids.items():
                try:
                    player_obj = await ensure_player_registered(db, competition.id, internal_id, competition.start_mmr)
                    player_objs_map[internal_id] = player_obj
                except Exception as e:
                     logger.error(f"Ошибка при регистрации игрока {username} (ID: {internal_id}) в соревновании {competition.id}: {e}")
                     errors.append(f"Ошибка при регистрации игрока {username}.")
            
            if errors:
                error_msg = "\n".join(errors)
                await message.reply(f"❌ Ошибки при регистрации участников:\n{error_msg}", disable_notification=True)
                return

            # 6. Определение внутреннего ID победителя
            winner_internal_id = user_internal_ids.get(winner_username)
            if not winner_internal_id:
                # Это маловероятно, если проверка выше прошла, но на всякий случай
                await message.reply(f"❌ Критическая ошибка: Победитель {winner_username} не найден после обработки.", disable_notification=True)
                return

            # 7. Расчет изменений MMR 
            mmr_changes = {} # internal_id -> mmr_delta
            errors_during_mmr_calc = [] # Ошибки, возникшие при расчете MMR

            # Получаем объекты Player для всех участников, чтобы узнать их текущий MMR
            player_objs_for_mmr_calc = {} # internal_id -> Player obj
            for internal_id in user_internal_ids.values():
                 player_obj = player_objs_map.get(internal_id)
                 if player_obj:
                     player_objs_for_mmr_calc[internal_id] = player_obj
                 # else: Если объект Player не найден, это ошибка, но она должна была возникнуть раньше.
                 # Мы просто пропустим его в расчете.

            # Для каждого участника рассчитываем его изменение MMR относительно каждого оппонента
            for internal_id, player_obj in player_objs_for_mmr_calc.items():
                player_current_mmr = player_obj.mmr
                is_player_winner = (internal_id == winner_internal_id)

                # Собираем MMR всех оппонентов (всех других участников)
                opponent_mmrs = [
                    opp_player.mmr for opp_id, opp_player in player_objs_for_mmr_calc.items()
                    if opp_id != internal_id
                ]

                if not opponent_mmrs:
                    # Теоретически возможно только если участник один, что странно для матча.
                    mmr_changes[internal_id] = 0
                    continue

                # --- Расчет изменения MMR ---
                try:
                    if competition.use_formula and competition.formula:
                        # --- ВАРИАНТ 1: Использование формулы ---
                        # Для простоты, сравниваем со средним MMR оппонентов.
                        # Более сложные сценарии (1v1, FFA с весами) требуют усложнения логики.
                        avg_opponent_mmr = sum(opponent_mmrs) / len(opponent_mmrs)
                        
                        # Рассчитываем изменение по формуле.
                        # Предполагаем, что формула дает абсолютное значение изменения за победу.
                        mmr_delta_abs = calculate_mmr_change_by_formula(competition, player_current_mmr, int(avg_opponent_mmr))
                        
                        # Применяем знак в зависимости от результата.
                        final_mmr_change = mmr_delta_abs if is_player_winner else -mmr_delta_abs
                        
                    else:
                        # --- ВАРИАНТ 2: Использование диапазонов ---
                        # Рассчитываем изменение для каждого матча "этот игрок vs один оппонент"
                        # и усредняем результат.
                        total_change = 0
                        num_matches = len(opponent_mmrs)
                        
                        for opp_mmr in opponent_mmrs:
                            mmr_change_for_pair = calculate_mmr_change_by_ranges(competition, player_current_mmr, opp_mmr, is_player_winner)
                            total_change += mmr_change_for_pair
                        
                        if num_matches > 0:
                            # Усредняем изменение по количеству "мини-матчей"
                            final_mmr_change = round(total_change / num_matches)
                        else:
                            final_mmr_change = 0
                    
                    mmr_changes[internal_id] = final_mmr_change
                    
                except Exception as e:
                    logger.error(f"Ошибка расчета MMR для пользователя ID {internal_id}: {e}", exc_info=True)
                    errors_during_mmr_calc.append(f"Ошибка расчета MMR для пользователя ID {internal_id}: {e}")
                    mmr_changes[internal_id] = 0 # В случае ошибки изменение 0

            # Проверяем, были ли ошибки при расчете
            if errors_during_mmr_calc:
                error_msg = "\n".join(errors_during_mmr_calc)
                await message.reply(
                    f"❌ Ошибки при расчете MMR:\n{error_msg}\nРезультаты могут быть некорректны.",
                    disable_notification=True
                )

            # 8. Подготовка данных для создания матча и обновления игроков
            match_participants_data = []

            # Используем participants_data, который содержит (username, achievements_list)
            for username, achievements_list in participants_data:
                internal_id = user_internal_ids.get(username)
                if not internal_id:
                    # Пропускаем, если пользователь не найден (хотя это уже проверено)
                    continue

                is_winner_flag = (internal_id == winner_internal_id)
                mmr_delta = mmr_changes.get(internal_id, 0) # Получаем РАССЧИТАННОЕ значение

                # Достижения от админа
                admin_achievements = achievements_list
                # achievements_gained_map[internal_id] = admin_achievements # Больше не нужно отдельно

                match_participants_data.append({
                    "user_id": internal_id,
                    "mmr_change": mmr_delta,
                    "is_winner": is_winner_flag,
                    "achievements": admin_achievements # Передаем достижения от админа
                })

            # 9. Создание матча и обновление статистики игроков
            try:
                 match = await crud.create_match(
                     db,
                     competition_id=competition.id,
                     winner_id=winner_internal_id,
                     participants=match_participants_data
                 )
                 logger.info(f"Матч ID {match.id} успешно создан для соревнования '{competition.name}' (ID: {competition.id})")

                 # create_match внутри себя вызывает update_player_stats_after_match
                 # для каждого участника, поэтому доп. обновление не нужно.

                 # 10. Формирование и отправка отчета
                 report_lines = [f"✅ Результаты матча (ID: {match.id}) для соревнования '{competition.name}' записаны:"]
                 for p_data in match_participants_data:
                     user_id = p_data['user_id']
                     mmr_change = p_data['mmr_change']
                     is_winner = p_data['is_winner']
                     aches = p_data['achievements']
                     
                     # Получаем username из player_obj для отчета
                     player_obj = player_objs_map.get(user_id)
                     if player_obj and player_obj.user:
                         user_display_name = f"@{player_obj.user.username}" if player_obj.user.username else f"ID:{player_obj.user.user_id}"
                     else:
                         user_display_name = f"ID:{user_id}" # На случай ошибки

                     status = "🏆 Победитель" if is_winner else "💀 Проигравший"
                     mmr_sign = "+" if mmr_change >= 0 else ""
                     ach_text = f", Достижения: {', '.join(aches)}" if aches else ""
                     report_lines.append(f" • {user_display_name}: {status}, MMR: {mmr_sign}{mmr_change}{ach_text}")

                 await message.reply("\n".join(report_lines), disable_notification=True)

            except Exception as e:
                 logger.error(f"Ошибка при создании матча или обновлении статистики: {e}", exc_info=True)
                 await message.reply(
                     f"❌ Произошла ошибка при записи результата матча: {e}",
                     disable_notification=True
                 )

        except Exception as e:
            logger.error(f"Ошибка в handle_match_outcome: {e}", exc_info=True)
            await message.reply(
                f"❌ Произошла внутренняя ошибка: {e}",
                disable_notification=True
            )
        # finally:
        #     # Сессия закроется автоматически благодаря async with

# --- Не забудь добавить недостающие функции в crud.py ---
# (См. следующий блок кода)