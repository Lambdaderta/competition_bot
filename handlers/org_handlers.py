from aiogram import Router, F, Bot # <-- ИЗМЕНЕНО: Добавил Bot для get_me()
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramAPIError # <-- НОВОЕ: Для обработки ошибок API
from utils.mmr_calculator import parse_range_input
from database import get_sessionmaker, crud
from sqlalchemy.ext.asyncio import AsyncSession


from keyboards.org_keyboard import (
    get_organizer_main_menu,
    get_rating_type_keyboard,
    get_cancel_creation_keyboard,
    get_yes_no_cancel_keyboard,
    get_add_range_rule_keyboard,
    get_confirmation_keyboard,
    get_bot_add_to_chat_keyboard,
    get_my_competitions_keyboard
)
from states.org_states import CompetitionCreation
from urllib.parse import urlparse 

import math 

ITEMS_PER_PAGE = 10

router = Router()

@router.callback_query(F.data == "role_organizer")
async def enter_organizer_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "Вы вошли в меню Организатора.",
        reply_markup=get_organizer_main_menu()
    )
    await callback.answer()

# --- Начало создания соревнования ---
@router.callback_query(F.data == "create_competition")
async def start_create_competition(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс создания соревнования, запрашивает название."""
    await state.set_state(CompetitionCreation.waiting_for_name)
    await callback.message.edit_text(
        "Введите название нового соревнования:",
        reply_markup=get_cancel_creation_keyboard()
    )
    await callback.answer()


# --- Получение названия соревнования ---
@router.message(CompetitionCreation.waiting_for_name)
async def process_competition_name(message: Message, state: FSMContext, bot: Bot): # <-- ИЗМЕНЕНО: Добавил bot: Bot
    """Обрабатывает введенное название соревнования и предлагает добавить бота в чат."""
    competition_name = message.text.strip()
    if not competition_name:
        await message.answer("Название не может быть пустым. Пожалуйста, введите название.")
        return # Остаемся в том же состоянии

    await state.update_data(name=competition_name)
    
    # --- ИЗМЕНЕНО: Вместо запроса ID чата, предлагаем добавить бота ---
    try:
        bot_me = await bot.get_me() # Получаем информацию о боте
        bot_username = bot_me.username
    except Exception:
        # На случай ошибки, используем захардкоженное имя (ЗАМЕНИ НА СВОЕ)
        # Лучше обработать ошибку более явно
        bot_username = "test_compet_bot" # <--- ЗАМЕНИ НА АКТУАЛЬНЫЙ USERNAME ТВОЕГО БОТА
        await message.answer("Не удалось автоматически получить имя бота. Используется имя по умолчанию.")

    await state.set_state(CompetitionCreation.waiting_for_bot_add_confirmation) # <-- ИЗМЕНЕНО: Новое состояние
    await message.answer(
        f"Название установлено: <b>{competition_name}</b>\n\n"
        "Теперь нужно выбрать чат, где будет проходить соревнование.\n"
        "1. Нажмите кнопку ниже, чтобы добавить бота в нужный чат.\n"
        "2. После добавления, вернитесь сюда и нажмите 'Я добавил бота'.",
        reply_markup=get_bot_add_to_chat_keyboard(bot_username) # <-- ИЗМЕНЕНО: Новая клавиатура
    )


# --- Обработка подтверждения добавления бота ---
@router.callback_query(CompetitionCreation.waiting_for_bot_add_confirmation, F.data == "bot_added_to_chat_confirmed")
async def bot_added_to_chat_confirmed(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Я добавил бота".
    Просит пользователя прислать @username или ссылку на чат.
    """
    await state.set_state(CompetitionCreation.waiting_for_chat_identifier) # <-- НОВОЕ: Следующее состояние
    await callback.message.edit_text(
        "Отлично! Теперь, пожалуйста, пришлите мне @юзернейм или прямую ссылку на чат, "
        "куда вы добавили бота (например, `@my_chat` или `https://t.me/my_chat`).\n\n"
        "<i>Если чат приватный и у него нет публичного юзернейма, "
        "убедитесь, что бот добавлен туда как участник, и пришлите любую ссылку-приглашение.</i>",
        reply_markup=get_cancel_creation_keyboard()
    )
    await callback.answer()
# --- КОНЕЦ НОВОГО ---

#  Получение идентификатора чата от пользователя ---
@router.message(CompetitionCreation.waiting_for_chat_identifier)
async def process_chat_identifier(message: Message, state: FSMContext, bot: Bot):
    """
    Обрабатывает введенный пользователем @username или ссылку на публичный чат.
    Поддерживает:
    - @username
    - https://t.me/username
    Пытается получить chat_id через getChat.
    """
    user_input = message.text.strip()

    # --- Логика извлечения @username ---
    chat_identifier = None
    if user_input.startswith('@'):
        # Прямой ввод юзернейма
        chat_identifier = user_input
    elif user_input.startswith('https://t.me/'):
        # Попытка извлечь юзернейм из ссылки
        parsed_url = urlparse(user_input)
        path_parts = parsed_url.path.strip('/').split('/')
        
        if len(path_parts) == 1 and path_parts[0]:
            # Ссылка вида https://t.me/username
            potential_username = path_parts[0]
            # Базовая проверка на допустимые символы в юзернейме
            if potential_username.replace('_', '').isalnum():
                chat_identifier = f"@{potential_username}"
        # Если формат не распознан или это ссылка-приглашение, chat_identifier останется None
    else:
        # Возможно, пользователь ввел юзернейм без @
        if user_input:
            chat_identifier = f"@{user_input.lstrip('@')}"

    if not chat_identifier:
        await message.answer(
            "Пожалуйста, отправьте @юзернейм публичной группы или прямую ссылку на неё (например, `@my_chat` или `https://t.me/my_chat`).\n"
            "⚠️ <b>Важно:</b> Группа должна быть публичной (иметь @username). "
            "Если у вашей группы нет юзернейма, сделайте её публичной, добавьте туда бота, а затем сделайте её приватной, если нужно."
        )
        # Остаемся в состоянии CompetitionCreation.waiting_for_chat_identifier
        return
    # --- Конец логики извлечения ---

    try:
        # Пытаемся получить информацию о чате
        chat_obj = await bot.get_chat(chat_id=chat_identifier)

        # Проверяем тип чата
        if chat_obj.type not in ["group", "supergroup"]:
            await message.answer(
                "Выбранный чат не является группой или супергруппой. "
                "Пожалуйста, укажите подходящий чат для соревнования."
            )
            # Остаемся в состоянии CompetitionCreation.waiting_for_chat_identifier
            return

        # Получаем ID чата
        chat_id = chat_obj.id

        # (Опционально) Можно проверить, является ли пользователь админом
        # member = await bot.get_chat_member(chat_id, message.from_user.id)
        # if member.status not in ['administrator', 'creator']:
        #     await message.answer("Вы не являетесь администратором этого чата. Пожалуйста, выберите другой чат.")
        #     return

        # Сохраняем chat_id в FSM
        await state.update_data(chat_id=chat_id)

        # Переходим к следующему шагу - вводу стартового MMR
        await state.set_state(CompetitionCreation.waiting_for_start_mmr)
        await message.answer(
            f"Чат <b>{chat_obj.title}</b> (ID: {chat_id}) успешно выбран для соревнования.\n"
            "Теперь введите стартовый MMR для участников (по умолчанию 0):",
            reply_markup=get_cancel_creation_keyboard()
        )

    except TelegramAPIError as e:
        # Обрабатываем ошибки API
        error_msg = str(e).lower()
        if "not found" in error_msg or "chat not found" in error_msg:
            await message.answer(
                f"Чат '{user_input}' не найден. Пожалуйста, убедитесь, что группа публичная и у неё есть @username, "
                f"и что бот @{(await bot.get_me()).username} добавлен в неё как участник."
            )
        elif "forbidden" in error_msg or "bot is not a member" in error_msg:
            bot_username = (await bot.get_me()).username
            await message.answer(
                f"Бот не состоит в чате '{user_input}'.\n"
                f"<b>Инструкция:</b>\n"
                f"1. Сделайте группу публичной (настройки группы -> Тип чата -> Публичная).\n"
                f"2. Добавьте бота @{bot_username} в эту группу как участника или администратора.\n"
                f"3. После добавления бота вы можете снова сделать группу приватной, если хотите.\n"
                f"4. Затем снова пришлите сюда @username или ссылку на группу."
            )
        else:
            # Другие ошибки API
            await message.answer(
                f"Ошибка при проверке чата '{user_input}': {e}. "
                f"Пожалуйста, попробуйте ещё раз или обратитесь к разработчику."
            )
        # Остаемся в состоянии CompetitionCreation.waiting_for_chat_identifier
    except Exception as e:
        # Другие непредвиденные ошибки
        await message.answer(
            f"Произошла неизвестная ошибка при обработке '{user_input}': {e}. "
            f"Пожалуйста, попробуйте ещё раз."
        )

# --- Получение стартового MMR ---
@router.message(CompetitionCreation.waiting_for_start_mmr)
async def process_start_mmr(message: Message, state: FSMContext):
    """Обрабатывает введенный стартовый MMR."""
    try:
        start_mmr = int(message.text.strip())
        if start_mmr < 0:
            raise ValueError("MMR не может быть отрицательным")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное неотрицательное целое число для стартового MMR.")
        return # Остаемся в том же состоянии

    await state.update_data(start_mmr=start_mmr)
    await state.set_state(CompetitionCreation.waiting_for_rating_type)
    await message.answer(
        "Выберите тип системы расчета рейтинга:",
        reply_markup=get_rating_type_keyboard()
    )

# --- Обработка отмены на любом этапе ---
@router.callback_query(F.data == "cancel_creation")
async def cancel_competition_creation(callback: CallbackQuery, state: FSMContext):
    """Отменяет процесс создания соревнования."""
    await state.clear()
    await callback.message.edit_text(
        "Создание соревнования отменено.",
        reply_markup=get_organizer_main_menu() # Возвращаем в меню организатора
    )
    await callback.answer()

# --- Обработка кнопки "Назад" в меню организатора ---
@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu_from_organizer(callback: CallbackQuery):
    """Возвращает в главное меню (логика в основном хендлере)."""
    # TODO: Это требует, чтобы главное меню было доступно отсюда.
    # Пока просто заглушка или вызов другой функции.
    from keyboards.main_menu import get_main_menu_keyboard # Предположим, такое есть
    await callback.message.edit_text(
        "Привет! Выберите свою роль:",
        reply_markup=get_main_menu_keyboard() # Эта функция должна быть определена в другом месте
    )
    await callback.answer()


# --- Выбор типа рейтинга ---
@router.callback_query(CompetitionCreation.waiting_for_rating_type, F.data.startswith("rating_type_"))
async def process_rating_type_choice(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор типа системы рейтинга."""
    rating_type = callback.data.split("_")[-1] # "formula" или "ranges"

    if rating_type == "formula":
        await state.update_data(use_formula=True)
        await state.set_state(CompetitionCreation.waiting_for_formula)
        # TODO: Добавить подробный гайд по формулам
        guide_text = (
            "Введите формулу для расчета изменения MMR.\n"
            "Например просто 10, или 25, тогда ммр будет изменться за победу и поражение на одно и то же число.\n"
            "Вы можете использовать 2 переменные: player_mmr, opponent_mmr\n"
            "Например: 10 * (player_mmr - opponent_mmr)"
            "Тогда ммр будет изменяться на разницу между ммр игроков помноженную на 10"
            "Введите формулу:"
        )
        await callback.message.edit_text(guide_text, reply_markup=get_cancel_creation_keyboard())
    elif rating_type == "ranges":
        await state.update_data(use_formula=False)
        # Инициализируем пустой список для правил
        await state.update_data(range_rules=[])
        await state.set_state(CompetitionCreation.waiting_to_add_range_rule)
        await callback.message.edit_text(
            "Настройка системы рейтинга на основе диапазонов разницы сил.\n\n"
            "Вы сможете добавить правила в формате:\n"
            "<code>Диапазон разницы -> Очки за победу -> Очки за поражение</code>\n\n"
            "Например: <code>0-99 -> 25 -> -10</code> или <code>500+ -> 50 -> 0</code> или <code>любой -> 20 -> -20</code>",
            reply_markup=get_add_range_rule_keyboard()
        )
    await callback.answer()

# --- Ввод формулы ---
@router.message(CompetitionCreation.waiting_for_formula)
async def process_formula_input(message: Message, state: FSMContext):
    """Обрабатывает введенную формулу."""
    formula = message.text.strip()
    if not formula:
        await message.answer("Формула не может быть пустой. Пожалуйста, введите формулу.")
        return

    await state.update_data(formula=formula)
    # После ввода формулы переходим к настройке дополнительных опций
    await state.set_state(CompetitionCreation.waiting_for_achievements_choice)
    await message.answer(
        "Формула сохранена.\n\nХотите настроить систему достижений?",
        reply_markup=get_yes_no_cancel_keyboard(yes_data="setup_achievements_yes", no_data="skip_achievements")
    )

#Ввод диапазона
@router.callback_query(CompetitionCreation.waiting_to_add_range_rule, F.data == "add_range_rule")
async def ask_for_range_diff(callback: CallbackQuery, state: FSMContext):
    """Просит пользователя ввести диапазон разницы."""
    await state.set_state(CompetitionCreation.waiting_for_range_diff)
    await callback.message.edit_text(
        "Введите диапазон разницы рейтингов соперников.\n"
        "Форматы:\n"
        "- <code>0-99</code>\n"
        "- <code>100-199</code>\n"
        "- <code>500+</code> (для 500 и выше)\n"
        "- <code>любой</code> (любая разница)\n\n"
        "Введите диапазон:",
        reply_markup=get_cancel_creation_keyboard()
    )
    await callback.answer()

# --- Завершение добавления правил диапазонов ---
@router.callback_query(CompetitionCreation.waiting_to_add_range_rule, F.data == "finish_ranges")
async def finish_adding_ranges(callback: CallbackQuery, state: FSMContext):
    """Завершает добавление правил диапазонов и переходит к следующему шагу."""
    # Переходим к настройке достижений
    await state.set_state(CompetitionCreation.waiting_for_achievements_choice)
    await callback.message.edit_text(
        "Настройка диапазонов завершена.\n\nХотите настроить систему достижений?",
        reply_markup=get_yes_no_cancel_keyboard(yes_data="setup_achievements_yes", no_data="skip_achievements")
    )
    await callback.answer()

# --- Получение диапазона разницы ---
@router.message(CompetitionCreation.waiting_for_range_diff)
async def process_range_diff(message: Message, state: FSMContext):
    """Обрабатывает введенный диапазон разницы."""
    range_input = message.text.strip()
    try:
        diff_min, diff_max = parse_range_input(range_input)
    except ValueError as e:
        await message.answer(f"Ошибка: {e}\nПожалуйста, введите корректный диапазон.")
        # Остаемся в том же состоянии
        return

    # Сохраняем диапазон во временное хранилище FSM
    await state.update_data(temp_range_diff=(diff_min, diff_max))
    await state.set_state(CompetitionCreation.waiting_for_win_points)
    await message.answer(
        f"Диапазон установлен: {range_input}.\n"
        "Введите количество очков MMR за победу в этом диапазоне (например, '25'):"
    )
    # Для этого шага не делаем отдельную клавиатуру, просто текстовый ввод

# --- Получение очков за победу ---
@router.message(CompetitionCreation.waiting_for_win_points)
async def process_win_points(message: Message, state: FSMContext):
    """Обрабатывает введенные очки за победу."""
    try:
        win_points = int(message.text.strip())
        if win_points <= 0:
            raise ValueError("Очки за победу должны быть положительными.")
    except ValueError as e:
        # Проверяем, является ли e уже ValueError, который мы выбросили
        if isinstance(e, ValueError) and "Очки" in str(e):
            await message.answer(str(e))
        else:
            await message.answer("Пожалуйста, введите корректное положительное целое число.")
        return

    await state.update_data(temp_win_points=win_points)
    await state.set_state(CompetitionCreation.waiting_for_lose_points)
    await message.answer(
        f"Очки за победу установлены: {win_points}.\n"
        "Введите количество очков MMR за поражение в этом диапазоне (например, '-10'):"
    )

# --- Получение очков за поражение ---
@router.message(CompetitionCreation.waiting_for_lose_points)
async def process_lose_points(message: Message, state: FSMContext):
    """Обрабатывает введенные очки за поражение и сохраняет правило."""
    try:
        lose_points = int(message.text.strip())
        if lose_points >= 0:
            raise ValueError("Очки за поражение должны быть отрицательными.")
    except ValueError as e:
        if isinstance(e, ValueError) and "Очки" in str(e):
            await message.answer(str(e))
        else:
            await message.answer("Пожалуйста, введите корректное отрицательное целое число.")
        return

    # Получаем все данные для нового правила
    user_data = await state.get_data()
    diff_min, diff_max = user_data['temp_range_diff']
    win_points = user_data['temp_win_points']

    # Создаем новое правило
    new_rule = {
        "diff_min": diff_min,
        "diff_max": diff_max,
        "win_points": win_points,
        "lose_points": lose_points
    }

    # Получаем список уже добавленных правил
    current_rules = user_data.get('range_rules', [])
    # Добавляем новое правило
    current_rules.append(new_rule)
    # Обновляем список в состоянии
    await state.update_data(range_rules=current_rules)

    # Сообщаем пользователю и предлагаем добавить еще или закончить
    await state.set_state(CompetitionCreation.waiting_to_add_range_rule)
    rule_str = f"({diff_min if diff_min is not None else '...'} - {diff_max if diff_max is not None else '...'}): +{win_points}/{-lose_points}"
    await message.answer(
        f"Правило добавлено: {rule_str}\n"
        "Хотите добавить еще одно правило?",
        reply_markup=get_add_range_rule_keyboard()
    )

@router.callback_query(CompetitionCreation.waiting_for_achievements_choice)
async def process_achievements_choice(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор настройки достижений."""
    if callback.data == "setup_achievements_yes":
        # Инициализируем пустой словарь для достижений
        await state.update_data(achievements={})
        await state.set_state(CompetitionCreation.waiting_for_achievement_name)
        await callback.message.edit_text(
            "Введите название первого достижения (или 'закончить' для перехода к рангам):",
            reply_markup=get_cancel_creation_keyboard()
        )
    else: # callback.data == "skip_achievements" или любой другой ответ "Нет"
        # Пропускаем настройку достижений
        await state.set_state(CompetitionCreation.waiting_for_ranks_choice)
        await callback.message.edit_text(
            "Хотите настроить ранговую систему? (Новичок, Бронза, Серебро и т.д.)",
            reply_markup=get_yes_no_cancel_keyboard(yes_data="setup_ranks_yes", no_data="skip_ranks")
        )
    await callback.answer()

# --- Получение названия достижения ---
@router.message(CompetitionCreation.waiting_for_achievement_name)
async def process_achievement_name(message: Message, state: FSMContext):
    """Обрабатывает введенное название достижения."""
    ach_name = message.text.strip()
    
    if ach_name.lower() == "закончить":
        # Переход к настройке рангов
        await state.set_state(CompetitionCreation.waiting_for_ranks_choice)
        await message.answer(
            "Настройка достижений завершена.\n\n"
            "Хотите настроить ранговую систему? (Новичок, Бронза, Серебро и т.д.)",
            reply_markup=get_yes_no_cancel_keyboard(yes_data="setup_ranks_yes", no_data="skip_ranks")
        )
        return

    if not ach_name:
        await message.answer("Название не может быть пустым. Пожалуйста, введите название.")
        return

    # Сохраняем название во временное хранилище
    await state.update_data(temp_achievement_name=ach_name)
    await state.set_state(CompetitionCreation.waiting_for_achievement_bonus)
    await message.answer(
        f"Название достижения: <b>{ach_name}</b>\n"
        "Введите бонус MMR за получение этого достижения (например, '5'):"
    )

# --- Получение бонуса MMR за достижение ---
@router.message(CompetitionCreation.waiting_for_achievement_bonus)
async def process_achievement_bonus(message: Message, state: FSMContext):
    """Обрабатывает введенный бонус MMR за достижение."""
    try:
        bonus = int(message.text.strip())
        if bonus < 0:
            raise ValueError("Бонус не может быть отрицательным.")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное неотрицательное целое число для бонуса MMR.")
        return

    # Получаем данные
    user_data = await state.get_data()
    ach_name = user_data['temp_achievement_name']
    
    # Получаем текущий словарь достижений
    current_achievements = user_data.get('achievements', {})
    # Добавляем новое достижение
    current_achievements[ach_name] = bonus
    # Обновляем состояние
    await state.update_data(achievements=current_achievements)
    
    # Сообщаем пользователю и предлагаем добавить еще или закончить
    await state.set_state(CompetitionCreation.waiting_for_achievement_name)
    await message.answer(
        f"Достижение добавлено: <b>{ach_name}</b> (+{bonus} MMR)\n"
        "Введите название следующего достижения (или 'закончить' для перехода к рангам):"
    )

# --- Пропуск настройки достижений (если был отдельный хендлер) ---
# Этот хендлер больше не нужен, логика полностью в process_achievements_choice

# --- Предложение настроить ранги ---
@router.callback_query(CompetitionCreation.waiting_for_ranks_choice)
async def process_ranks_choice(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор настройки рангов."""
    if callback.data == "setup_ranks_yes":
        # Инициализируем пустой список для рангов
        await state.update_data(ranks=[])
        await state.set_state(CompetitionCreation.waiting_for_rank_name)
        await callback.message.edit_text(
            "Введите название первого ранга (например, 'Новичок') (или 'закончить' для подтверждения):",
            reply_markup=get_cancel_creation_keyboard()
        )
    else: # callback.data == "skip_ranks" или любой другой ответ "Нет"
        # Пропускаем настройку рангов и переходим к подтверждению
        await state.set_state(CompetitionCreation.waiting_for_confirmation)
        # --- Собираем данные для предварительного просмотра ---
        # (Этот блок кода уже есть в вашем обработчике, я его повторю ниже для полноты)
        await show_competition_preview(callback.message, state)
    await callback.answer()

# --- Получение названия ранга ---
@router.message(CompetitionCreation.waiting_for_rank_name)
async def process_rank_name(message: Message, state: FSMContext):
    """Обрабатывает введенное название ранга."""
    rank_name = message.text.strip()
    
    if rank_name.lower() == "закончить":
        # Переход к финальному подтверждению
        await state.set_state(CompetitionCreation.waiting_for_confirmation)
        # --- Собираем данные для предварительного просмотра ---
        await show_competition_preview(message, state) # Используем message, так как это Message хендлер
        return

    if not rank_name:
        await message.answer("Название не может быть пустым. Пожалуйста, введите название.")
        return

    # Сохраняем название во временное хранилище
    await state.update_data(temp_rank_name=rank_name)
    await state.set_state(CompetitionCreation.waiting_for_rank_mmr_threshold)
    await message.answer(
        f"Название ранга: <b>{rank_name}</b>\n"
        "Введите MMR-порог для этого ранга (например, '0' для начального ранга):"
    )

# --- Получение MMR-порога для ранга ---
@router.message(CompetitionCreation.waiting_for_rank_mmr_threshold)
async def process_rank_mmr_threshold(message: Message, state: FSMContext):
    """Обрабатывает введенный MMR-порог для ранга."""
    try:
        mmr_threshold = int(message.text.strip())
        if mmr_threshold < 0:
            raise ValueError("MMR-порог не может быть отрицательным.")
    except ValueError:
        await message.answer("Пожалуйста, введите корректное неотрицательное целое число для MMR-порога.")
        return

    # Получаем данные
    user_data = await state.get_data()
    rank_name = user_data['temp_rank_name']
    
    # Создаем новый ранг
    new_rank = {
        "name": rank_name,
        "mmr_threshold": mmr_threshold
    }

    # Получаем текущий список рангов
    current_ranks = user_data.get('ranks', [])
    # Добавляем новый ранг
    current_ranks.append(new_rank)
    # Обновляем состояние
    await state.update_data(ranks=current_ranks)
    
    # Сообщаем пользователю и предлагаем добавить еще или закончить
    await state.set_state(CompetitionCreation.waiting_for_rank_name)
    await message.answer(
        f"Ранг добавлен: <b>{rank_name}</b> (Порог: {mmr_threshold} MMR)\n"
        "Введите название следующего ранга (или 'закончить' для подтверждения):"
    )

# --- Пропуск настройки рангов (если был отдельный хендлер) ---
# Этот хендлер больше не нужен, логика полностью в process_ranks_choice

# --- Вспомогательная функция для отображения предварительного просмотра ---
# Вынесем логику предварительного просмотра в отдельную функцию, чтобы не дублировать код
async def show_competition_preview(message, state: FSMContext):
    """Отображает сводную информацию о создаваемом соревновании."""
    user_data = await state.get_data()
    preview_text = "<b>Предварительный просмотр соревнования:</b>\n\n"
    preview_text += f"<b>Название:</b> {user_data.get('name', 'N/A')}\n"
    preview_text += f"<b>ID чата:</b> {user_data.get('chat_id', 'N/A')}\n"
    preview_text += f"<b>Стартовый MMR:</b> {user_data.get('start_mmr', 0)}\n"
    
    if user_data.get('use_formula', False):
        preview_text += f"<b>Тип рейтинга:</b> Формула\n"
        preview_text += f"<b>Формула:</b> <code>{user_data.get('formula', 'N/A')}</code>\n"
    else:
        preview_text += f"<b>Тип рейтинга:</b> Диапазоны\n"
        rules = user_data.get('range_rules', [])
        if rules:
            preview_text += "<b>Правила диапазонов:</b>\n"
            for rule in rules[:3]:
                preview_text += f"  - Разница {rule.get('diff_min')} - {rule.get('diff_max')}: +{rule.get('win_points')}/-{abs(rule.get('lose_points', 0))}\n"
            if len(rules) > 3:
                preview_text += f"  ... и еще {len(rules) - 3} правил.\n"
        else:
            preview_text += "<b>Правила диапазонов:</b> Не добавлены\n"

    # --- НОВОЕ: Отображение достижений ---
    achievements = user_data.get('achievements', {})
    if achievements:
        preview_text += "<b>Достижения:</b>\n"
        for ach_name, bonus in list(achievements.items())[:3]: # Покажем первые 3
            preview_text += f"  - <b>{ach_name}:</b> +{bonus} MMR\n"
        if len(achievements) > 3:
            preview_text += f"  ... и еще {len(achievements) - 3} достижений.\n"
    else:
        preview_text += "<b>Достижения:</b> Не настроены\n"
    # ------------------------------------

    ranks = user_data.get('ranks', [])
    if ranks:
        # Сортируем по порогу для корректного отображения
        sorted_ranks = sorted(ranks, key=lambda r: r['mmr_threshold'])
        preview_text += "<b>Ранги:</b>\n"
        for rank in sorted_ranks[:3]: # Покажем первые 3
            preview_text += f"  - <b>{rank['name']}:</b> от {rank['mmr_threshold']} MMR\n"
        if len(sorted_ranks) > 3:
            preview_text += f"  ... и еще {len(sorted_ranks) - 3} рангов.\n"
    else:
        preview_text += "<b>Ранги:</b> Не настроены\n"
    # ---------------------------------

    preview_text += "\nВсе верно?"
    await message.answer(preview_text, reply_markup=get_confirmation_keyboard())


# Подтверждение всей шняги


# handlers/org_handlers.py
# ... (все необходимые импорты вверху файла, включая get_sessionmaker, crud, AsyncSession, F, Router и т.д.) ...

@router.callback_query(CompetitionCreation.waiting_for_confirmation, F.data == "confirm_creation")
async def confirm_competition_creation(callback: CallbackQuery, state: FSMContext):
    """Подтверждает создание соревнования и вызывает crud.create_competition."""
    
    # 1. Собираем все данные из состояния FSM
    user_data = await state.get_data()
    
    name = user_data['name']
    chat_id = user_data['chat_id']
    start_mmr = user_data['start_mmr']
    use_formula = user_data['use_formula']
    
    # 2. Формируем словарь данных для создания соревнования
    comp_data = {
        "name": name,
        "chat_id": chat_id,
        "start_mmr": start_mmr,
        "use_formula": use_formula,
    }
    
    if use_formula:
        comp_data["formula"] = user_data.get('formula')
    else:
        comp_data["range_rules"] = user_data.get('range_rules', [])
        
    comp_data["achievements"] = user_data.get('achievements', {})
    comp_data["ranks"] = user_data.get('ranks', [])

    # 3. Получаем фабрику сессий из database/__init__.py
    AsyncSessionLocal = get_sessionmaker()

    # 4. Используем async with для автоматического управления сессией
    # Это гарантирует, что сессия будет закрыта, даже если произойдет ошибка
    async with AsyncSessionLocal() as db:
        try:
            # 5. Получаем/создаем пользователя в БД
            telegram_user_id = callback.from_user.id
            username = callback.from_user.username or ""
            full_name = f"{callback.from_user.first_name or ''} {callback.from_user.last_name or ''}".strip()
            
            db_user = await crud.get_or_create_user(db, telegram_user_id, username, full_name)
            internal_creator_id = db_user.id
            comp_data["creator_id"] = internal_creator_id

            # 6. Создаем соревнование через crud
            # Предполагается, что crud.create_competition сама вызывает await db.commit() и await db.refresh()
            competition = await crud.create_competition(db, **comp_data)
            
            # 7. Отправляем сообщение об успехе пользователю
            await callback.message.edit_text(
                f"✅ Соревнование <b>'{competition.name}'</b> успешно создано!\n"
                f"ID: {competition.id}\n"
                f"Чат: {competition.chat_id}\n"
                f"Тип рейтинга: {'Формула' if competition.use_formula else 'Диапазоны'}\n"
            )
            
        except Exception as e:
            import logging
            logging.error(f"Ошибка создания соревнования: {e}", exc_info=True)
            await callback.message.edit_text(
                f"❌ Ошибка при создании соревнования: {str(e)}\n" 
                f"Пожалуйста, попробуйте еще раз или обратитесь к разработчику."
            )
            
    # 9. Очищаем состояние FSM и отвечаем на callback
    await state.clear()
    await callback.answer()




# ОБРАБОТКА "МОИ СОРЕВНОВАНИЯ"

@router.callback_query(F.data == "my_competitions")
async def show_my_competitions(callback: CallbackQuery):
    """Показывает список соревнований, где пользователь админ, с пагинацией."""
    await show_my_competitions_page(callback, page=1)

async def show_my_competitions_page(callback: CallbackQuery, page: int):
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

            # Получаем ВСЕ соревнования, где пользователь админ
            # Это может быть неэффективно для очень больших списков, но для начала сойдет
            # В будущем можно оптимизировать с помощью JOIN и LIMIT/OFFSET в SQL
            all_competitions = await crud.get_administered_competitions(db, internal_user_id)
            
            if not all_competitions:
                await callback.message.edit_text(
                    "У вас нет соревнований, где вы являетесь администратором.",
                    reply_markup=get_organizer_main_menu() # Возвращаем в меню организатора
                )
                await callback.answer()
                return

            total_items = len(all_competitions)
            total_pages = math.ceil(total_items / ITEMS_PER_PAGE) or 1 # Минимум 1 страница

            # Проверяем корректность номера страницы
            if page < 1:
                page = 1
            elif page > total_pages:
                page = total_pages

            # Вычисляем индексы для среза
            start_index = (page - 1) * ITEMS_PER_PAGE
            end_index = start_index + ITEMS_PER_PAGE
            competitions_on_page = all_competitions[start_index:end_index]

            # Формируем текст сообщения
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

            # Отправляем/редактируем сообщение с клавиатурой пагинации
            await callback.message.edit_text(
                message_text,
                reply_markup=get_my_competitions_keyboard(competitions_on_page, page, total_pages, ITEMS_PER_PAGE)
            )
            await callback.answer()

        except Exception as e:
            await callback.message.edit_text(
                f"❌ Произошла ошибка: {e}",
                reply_markup=get_organizer_main_menu()
            )
            await callback.answer()

# --- Хендлер для навигации по страницам ---
@router.callback_query(F.data.startswith("my_comps_page_"))
async def navigate_my_competitions(callback: CallbackQuery):
    """Обрабатывает нажатие кнопок навигации по страницам 'Мои соревнования'."""
    try:
        page_num = int(callback.data.split("_")[-1])
        await show_my_competitions_page(callback, page=page_num)
    except (ValueError, IndexError):
        await callback.answer("Ошибка навигации.", show_alert=True)