# states/organizer_states.py
from aiogram.fsm.state import State, StatesGroup

class CompetitionCreation(StatesGroup):
    # --- Фаза 1: Основные данные ---
    waiting_for_name = State()         # Шаг 1: Название
    # waiting_for_chat_id = State()      # Шаг 2: ID чата (пока упрощенно)
    waiting_for_bot_add_confirmation = State() # НОВОЕ: Ожидание подтверждения добавления бота
    waiting_for_chat_identifier = State()
    waiting_for_start_mmr = State()    # Шаг 3: Стартовый MMR

    # --- Фаза 2: Система рейтинга ---
    waiting_for_rating_type = State()  # Шаг 4: Выбор типа (Формула/Диапазоны)
    
    # --- Фаза 2.1: Ввод формулы ---
    waiting_for_formula = State()      # Шаг 5a: Ввод формулы
    
    # --- Фаза 2.1: Ввод диапазонов ---
    waiting_to_add_range_rule = State() # Шаг 5b: Предложение добавить правило
    waiting_for_range_diff = State()    # Шаг 5b.1: Ввод диапазона разницы
    waiting_for_win_points = State()    # Шаг 5b.2: Ввод очков за победу
    waiting_for_lose_points = State()   # Шаг 5b.3: Ввод очков за поражение

    # --- Фаза 3: Дополнительно ---
    
    # --- НОВОЕ: Достижения ---
    waiting_for_achievements_choice = State()
    waiting_for_achievement_name = State()
    waiting_for_achievement_bonus = State()
    # -------------------------
    
    # --- НОВОЕ: Ранги ---
    waiting_for_ranks_choice = State()
    waiting_for_rank_name = State()
    waiting_for_rank_mmr_threshold = State()
    # -------------------

    # --- Фаза 4: Подтверждение ---
    waiting_for_confirmation = State()        # Шаг 8: Подтверждение создания
