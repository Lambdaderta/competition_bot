# utils/mmr_calculator.py
import math
import logging
from typing import List, Dict, Any, Optional, Tuple, Union

logger = logging.getLogger(__name__)

def parse_range_input(range_str: str) -> Tuple[Optional[int], Optional[int]]:
    range_str = range_str.strip().lower()
    
    if range_str in ["любой", "any", ""]:
        return (None, None)
        
    if "+" in range_str:
        parts = range_str.split("+")
        if len(parts) == 2 and parts[1] == "" and parts[0].lstrip('-').isdigit():
            return (int(parts[0]), None)
        else:
            raise ValueError("Некорректный формат диапазона 'N+'. Пример: '500+'")
            
    elif "-" in range_str:
        parts = range_str.split("-")
        cleaned_parts = []
        i = 0
        while i < len(parts):
            if parts[i] == "" and i + 1 < len(parts) and parts[i+1].isdigit():
                cleaned_parts.append(f"-{parts[i+1]}")
                i += 2 
            else:
                cleaned_parts.append(parts[i])
                i += 1
                
        if len(cleaned_parts) == 2:
            try:
                min_val = int(cleaned_parts[0])
                max_val = int(cleaned_parts[1])
                if min_val > max_val:
                    raise ValueError("Минимальное значение диапазона не может быть больше максимального.")
                return (min_val, max_val)
            except ValueError:
                raise ValueError("Некорректные числа в диапазоне 'N-M'. Пример: '0-99' или '-50-49'")
        else:
             raise ValueError("Некорректный формат диапазона 'N-M'. Пример: '0-99'")
    else:
        raise ValueError("Некорректный формат диапазона. Используйте 'N-M', 'N+' или 'любой'.")


def calculate_mmr_change_by_formula(
    competition: Any, # Предполагается объект Competition или словарь с 'formula'
    player_mmr: int,
    opponent_mmr: int
) -> int:
    """
    Рассчитывает изменение MMR для игрока по заданной формуле.
    
    Формула может использовать переменные:
    - player_mmr: MMR игрока
    - opponent_mmr: MMR оппонента
    
    Пример формулы: "20" -> всегда +20 за победу, -20 за поражение.
    Пример формулы: "10 * (player_mmr - opponent_mmr)" -> зависит от разницы.
    
    ВАЖНО: Эта реализация использует eval, что может быть небезопасно.
    В продакшене лучше использовать безопасный парсер/интерпретатор формул.
    
    Args:
        competition: Объект соревнования, у которого есть атрибут 'formula'.
        player_mmr (int): Текущий MMR игрока.
        opponent_mmr (int): Текущий MMR оппонента.
        
    Returns:
        int: Рассчитанное изменение MMR (может быть отрицательным).
    """
    if not competition.use_formula or not competition.formula:
        raise ValueError("Соревнование не использует формулу или формула пуста.")
    
    formula = competition.formula.strip()
    if not formula:
         raise ValueError("Формула пуста.")

    # --- ОЧЕНЬ ПРОСТОЙ И НЕБЕЗОПАСНЫЙ способ вычисления формулы ---
    # В реальном приложении НЕ рекомендуется использовать eval напрямую.
    # Лучше использовать библиотеки типа `simpleeval` или написать свой парсер.
    try:
        # Доступные переменные для формулы
        # Ограничиваем доступные имена для безопасности (минимальная защита)
        allowed_names = {
            "player_mmr": player_mmr,
            "opponent_mmr": opponent_mmr,
            # Можно добавить математические константы и функции
            "abs": abs, "min": min, "max": max, "round": round,
            "pow": pow, "math": math # Даем доступ к модулю math
        }
        # Вычисляем формулу
        # eval_formula = eval(formula, {"__builtins__": {}}, allowed_names)
        # Более безопасный eval (все равно не идеал)
        eval_formula = eval(formula, {"__builtins__": None}, allowed_names)
        
        # Предполагаем, что формула дает изменение MMR за победу.
        # За поражение будет отрицательное значение.
        # Если результат float, округляем до int.
        change = int(eval_formula) if isinstance(eval_formula, (int, float)) else 0
        logger.debug(f"Формула '{formula}' для MMR игрока {player_mmr} vs {opponent_mmr} дала изменение: {change}")
        return change
    except Exception as e:
        logger.error(f"Ошибка вычисления формулы '{formula}': {e}")
        # В случае ошибки возвращаем 0 или выбрасываем исключение
        # Лучше явно обработать в вызывающем коде
        raise ValueError(f"Ошибка в формуле '{formula}': {e}")
    

def calculate_mmr_change_by_ranges(
    competition: Any, # Предполагается объект Competition или словарь с 'range_rules'
    player_mmr: int,
    opponent_mmr: int,
    is_winner: bool
) -> int:
    """
    Рассчитывает изменение MMR для игрока на основе диапазонов разницы рейтингов.
    
    Args:
        competition: Объект соревнования, у которого есть атрибут 'range_rules'.
        player_mmr (int): Текущий MMR игрока.
        opponent_mmr (int): Текущий MMR оппонента.
        is_winner (bool): Выиграл ли игрок этот матч.
        
    Returns:
        int: Рассчитанное изменение MMR.
    """
    if competition.use_formula or not competition.range_rules:
        raise ValueError("Соревнование использует формулу или правила диапазонов отсутствуют.")
    
    # Вычисляем разницу рейтингов: Рейтинг_Соперника - Мой_Рейтинг
    mmr_diff = abs(opponent_mmr - player_mmr)
    logger.debug(f"Разница MMR (оппонент {opponent_mmr} - игрок {player_mmr}) = {mmr_diff}")

    # Ищем подходящее правило
    applicable_rule = None
    for rule in competition.range_rules:
        diff_min = rule.get('diff_min')
        diff_max = rule.get('diff_max')
        
        # Проверка, попадает ли mmr_diff в диапазон [diff_min, diff_max)
        # Или если diff_min/diff_max None, это "любой" диапазон (обычно ставится последним)
        if (diff_min is None or mmr_diff >= diff_min) and (diff_max is None or mmr_diff < diff_max):
            applicable_rule = rule
            break # Берем первое подходящее правило
    
    if not applicable_rule:
        logger.warning(f"Не найдено правило диапазона для разницы MMR {mmr_diff}. Изменение MMR будет 0.")
        return 0

    # Определяем изменение MMR на основе правила и результата
    if is_winner:
        mmr_change = applicable_rule.get('win_points', 0)
    else:
        mmr_change = applicable_rule.get('lose_points', 0)
    
    logger.debug(f"Применено правило: {applicable_rule}. Изменение MMR: {mmr_change}")
    return mmr_change

# --- Вспомогательная функция для определения общего изменения MMR в матче с несколькими участниками ---
# (Может быть полезна в handlers/match_handlers.py)

def calculate_mmr_changes_for_match(
    competition: Any,
    match_participants: List[Dict[str, Any]] # Список словарей с 'user_id', 'mmr' (текущий MMR пользователя)
) -> Dict[int, int]:
    """
    Рассчитывает изменение MMR для всех участников матча.
    
    Эта функция предполагает, что матч "каждый с каждым" или что-то подобное,
    где нужно сравнить MMR каждого участника со средним MMR остальных или друг с другом.
    Логика может сильно варьироваться в зависимости от типа игры/матча.
    
    Этот пример демонстрирует расчет относительно среднего MMR оппонентов.
    
    Args:
        competition: Объект соревнования.
        match_participants: Список словарей с информацией об участниках.
                           Каждый словарь должен содержать 'user_id' и 'mmr'.
                           Также может содержать 'is_winner' для определения результата.
                           
    Returns:
        Dict[int, int]: Словарь, где ключ - user_id, значение - изменение MMR.
    """
    if not match_participants:
        return {}

    changes = {}
    
    # Простой пример: каждый участник выигрывает/проигрывает у "среднего оппонента"
    # или рассчитывается индивидуально, если известны пары.
    # Для простоты предположим, что есть один победитель и все остальные - проигравшие.
    # Или более общий случай: у каждого есть свой результат (is_winner).
    
    # 1. Найдем победителей и проигравших
    winners = [p for p in match_participants if p.get('is_winner', False)]
    losers = [p for p in match_participants if not p.get('is_winner', False)]
    
    # Если нет явных победителей/проигравших, можно считать по другому критерию
    # Например, игрок с максимальным mmr считается "условным победителем" для расчета относительно среднего
    
    # 2. Рассчитываем для каждого участника
    for participant in match_participants:
        user_id = participant['user_id']
        player_mmr = participant['mmr']
        
        # Определяем результат для этого участника
        is_winner = participant.get('is_winner', False)
        
        # Для расчета берем средний MMR оппонентов
        opponents = [p for p in match_participants if p['user_id'] != user_id]
        if not opponents:
            # Если участник один (редко, но возможно), изменение 0
            changes[user_id] = 0
            continue
            
        avg_opponent_mmr = sum(op['mmr'] for op in opponents) / len(opponents)
        
        # Рассчитываем изменение MMR
        if competition.use_formula:
            mmr_delta = calculate_mmr_change_by_formula(competition, player_mmr, int(avg_opponent_mmr))
            # Если игрок выиграл, применяем положительное изменение, иначе отрицательное
            # (если формула уже учитывает знак, это может быть избыточно)
            # Предположим, формула дает абсолютное значение изменения за победу
            final_change = mmr_delta if is_winner else -mmr_delta
        else:
            # Используем диапазоны. Берем среднего оппонента для определения диапазона.
            final_change = calculate_mmr_change_by_ranges(competition, player_mmr, int(avg_opponent_mmr), is_winner)
            
        changes[user_id] = final_change
        
    return changes