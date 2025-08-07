# keyboards/organizer_keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Главное меню Организатора ---
def get_organizer_main_menu() -> InlineKeyboardMarkup:
    """Клавиатура главного меню для роли 'Организатор'."""
    keyboard = [
        [InlineKeyboardButton(text="Создать соревнование", callback_data="create_competition")],
        [InlineKeyboardButton(text="Мои соревнования", callback_data="my_competitions")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Кнопки выбора типа рейтинга ---
def get_rating_type_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора типа системы рейтинга."""
    keyboard = [
        [InlineKeyboardButton(text="Формула", callback_data="rating_type_formula")],
        [InlineKeyboardButton(text="Диапазоны", callback_data="rating_type_ranges")],
        [InlineKeyboardButton(text="Назад", callback_data="cancel_creation")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Кнопки Да/Нет/Отмена для различных вопросов ---
def get_yes_no_cancel_keyboard(yes_data: str = "yes", no_data: str = "no", cancel_data: str = "cancel_creation") -> InlineKeyboardMarkup:
    """Универсальная клавиатура Да/Нет/Отмена."""
    keyboard = [
        [
            InlineKeyboardButton(text="Да", callback_data=yes_data),
            InlineKeyboardButton(text="Нет", callback_data=no_data),
        ],
        [InlineKeyboardButton(text="Отменить создание", callback_data=cancel_data)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Кнопки для добавления диапазонов ---
def get_add_range_rule_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для предложения добавить правило диапазона."""
    keyboard = [
        [InlineKeyboardButton(text="Добавить правило", callback_data="add_range_rule")],
        [InlineKeyboardButton(text="Закончить добавление", callback_data="finish_ranges")],
        [InlineKeyboardButton(text="Отменить создание", callback_data="cancel_creation")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Кнопка отмены ---
def get_cancel_creation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены создания."""
    keyboard = [
        [InlineKeyboardButton(text="Отменить создание", callback_data="cancel_creation")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Кнопки подтверждения ---
def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания."""
    keyboard = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_creation")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_creation")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_bot_add_to_chat_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой для добавления бота в чат.
    :param bot_username: Имя пользователя бота (без @).
    """
    add_bot_url = f"https://t.me/{bot_username}?startgroup=start"
    
    keyboard = [
        [
            InlineKeyboardButton(
                text="Добавить бота в чат/группу",
                url=add_bot_url # Открывает окно выбора чата в Telegram
            )
        ],
        [
            InlineKeyboardButton(
                text="✅ Я добавил бота",
                callback_data="bot_added_to_chat_confirmed" # Этот callback будем ловить
            )
        ],
        [
            InlineKeyboardButton(text="Отменить создание", callback_data="cancel_creation"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)



def get_my_competitions_keyboard(
    competitions: list, page: int, total_pages: int, items_per_page: int = 5
) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для отображения списка соревнований с пагинацией.

    :param competitions: Список объектов Competition для текущей страницы.
    :param page: Номер текущей страницы (начиная с 1).
    :param total_pages: Общее количество страниц.
    :param items_per_page: Количество элементов на странице.
    :return: InlineKeyboardMarkup.
    """
    keyboard = []

    # Добавляем кнопки для каждого соревнования на странице
    for comp in competitions:
        button_text = f"{comp.name} (ID: {comp.id})"
        # Предполагаем, что будет callback_data для выбора соревнования, например, "view_comp_{id}"
        # Пока просто заглушка, можно расширить до меню управления соревнованием
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"view_comp_{comp.id}")])

    # Добавляем кнопки навигации
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="<< Назад", callback_data=f"my_comps_page_{page - 1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперед >>", callback_data=f"my_comps_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    # Кнопка "Назад" в меню организатора
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)