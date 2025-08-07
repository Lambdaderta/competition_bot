from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from keyboards.main_menu import get_main_menu_keyboard

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == 'private':
        await message.answer(
            "👋 Привет! Добро пожаловать в бот для управления соревнованиями!\n\n"
            "Выберите свою роль:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer("Эта команда доступна только в личных сообщениях.")


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    """Возвращает пользователя в главное меню с выбором роли."""
    await callback.message.edit_text(
        "Выберите свою роль:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "role_participant")
async def enter_participant_menu(callback: CallbackQuery):
    """Обработчик нажатия кнопки 'Участник'."""
    await callback.message.edit_text(
        "Вы выбрали роль 'Участник'.\n"
        "Эта функция пока в разработке. Здесь будет список соревнований и т.д.",
        reply_markup=None 
    )
    await callback.answer()
