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


@router.message(Command("help"))
async def cmd_start(message: Message):
    await message.answer(
        "<b>👋 Привет! У бота есть несколько команд:</b>\n\n"
        "/start - Основная команда бота, нажмите ее и вам будут доступны почти все функции бота.\n\n"
        "<b>топ 'название соревнования' N</b>\n '/' использовать не нужно - команда, которая выводит топ игроков в соревновании по ммр. N - число, топ сколько хотите вывести, по умолчанию 30\n\n"
        "<b>стат 'название соревнования'</b>\n '/' использовать не нужно - показывает вашу статистику по соревнованию, также доступно через кнопки в режиме участника.\n\n"
        "<b>/add_admin - команда для добавления админа в соревнование.</b>\n Админ может записывать исходы боев с помощью команды /исход, по умолчанию может только создатель.\n\n"
        "<b>/исход или /Исход - команда для записи итога одного боя.</b>\nДоступно только админам соревнования. Для подробной инструкции по использованию просто напишите /исход в чате с совернованием (в чате с ботом не срабоатет)"
        )


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    """Возвращает пользователя в главное меню с выбором роли."""
    await callback.message.edit_text(
        "Выберите свою роль:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()



