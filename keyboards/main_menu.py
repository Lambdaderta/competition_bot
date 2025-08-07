# keyboards/main_menu.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура главного меню с выбором роли."""
    keyboard = [
        [InlineKeyboardButton(text="🏆 Организатор", callback_data="role_organizer")],
        [InlineKeyboardButton(text="🎮 Участник", callback_data="role_participant")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
