# keyboards/organizer_keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Главное меню Организатора ---
def get_player_main_menu() -> InlineKeyboardMarkup:
    """Клавиатура главного меню для роли 'Организатор'."""
    keyboard = [
        [InlineKeyboardButton(text="Мои соревнования", callback_data="my_played_competitions")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)




def get_player_competitions_keyboard(
    competitions: list, page: int, total_pages: int, items_per_page: int = 5
) -> InlineKeyboardMarkup:
    keyboard = []

    for comp in competitions:
        button_text = f"{comp.name} (ID: {comp.id})"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"view_comp_{comp.id}")])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="<< Назад", callback_data=f"player_comps_page_{page - 1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Вперед >>", callback_data=f"player_comps_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


