import time
from typing import List, Dict, Any, Optional
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, distinct

from sqlalchemy.orm import selectinload

from sqlalchemy import select

import logging

logger = logging.getLogger(__name__)

from . import models

# ---- User CRUD ----
async def get_or_create_user(db: AsyncSession, user_id: int, username: str, full_name: str) -> models.User:
    """
    Получает пользователя по user_id (Telegram ID) или создает нового, если не найден.
    Обновляет username и full_name, если они изменились.
    """
    # --- ИСПРАВЛЕНО: Упрощенный и правильный запрос по user_id ---
    # Выполняем асинхронный запрос
    result = await db.execute(select(models.User).where(models.User.user_id == user_id))
    user = result.scalars().first() # Получаем первый (и скорее всего единственный) результат
    # ------------------------------------------------------------
    
    if not user:
        # Пользователь не найден, создаем нового
        user = models.User(user_id=user_id, username=username, full_name=full_name)
        db.add(user)
        try:
            await db.commit()
            # Обычно не нужно refresh, если мы только что добавили и не обращаемся к связям
            # await db.refresh(user) 
        except IntegrityError:
            # Возможна гонка: другой процесс мог создать пользователя одновременно
            await db.rollback()
            # Повторно пытаемся получить пользователя
            result = await db.execute(select(models.User).where(models.User.user_id == user_id))
            user = result.scalars().first()
            if not user:
                # Если всё ещё не найден, это странно, бросаем исключение
                raise RuntimeError(f"Не удалось создать или получить пользователя с user_id={user_id}")
    else:
        # Пользователь найден, проверяем, нужно ли обновить данные
        updated = False
        if user.username != username:
            user.username = username
            updated = True
        if user.full_name != full_name:
            user.full_name = full_name
            updated = True
        if updated:
            # Если были изменения, коммитим
            await db.commit()
            # await db.refresh(user) # Опционально
    
    # Возвращаем объект пользователя
    return user

async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[models.User]: 
    """Получает пользователя по его Telegram ID."""
    result = await db.execute(select(models.User).where(models.User.user_id == user_id)) 
    return result.scalars().first() 


# ---- Competition CRUD ----
async def create_competition( 
    db: AsyncSession, 
    name: str,
    chat_id: int,
    creator_id: int,
    start_mmr: int = 0,
    use_formula: bool = False,
    formula: Optional[str] = None,
    range_rules: Optional[List[Dict[str, Any]]] = None,
    achievements: Optional[Dict[str, int]] = None,
    ranks: Optional[List[Dict[str, Any]]] = None
) -> models.Competition:
    """
    Создает новое соревнование.
    creator_id - внутренний ID пользователя (User.id).
    """
    competition = models.Competition(
        name=name,
        chat_id=chat_id,
        creator_id=creator_id,
        start_mmr=max(start_mmr, 0),
        use_formula=use_formula,
        formula=formula,
        range_rules=range_rules or [],
        achievements=achievements or {},
        ranks=ranks or [],
        admins=[creator_id]
    )
    db.add(competition)
    await db.commit()      
    await db.refresh(competition) 
    return competition

async def get_competition_by_name(db: AsyncSession, name: str) -> Optional[models.Competition]: 
    """Получает соревнование по его названию."""
    result = await db.execute(
        select(models.Competition)
        .where(models.Competition.name == name)
    )
    return result.scalars().first()


async def get_competition_by_id(db: AsyncSession, comp_id: int) -> Optional[models.Competition]: 
    """Получает соревнование по его внутреннему ID."""
    result = await db.execute(select(models.Competition).where(models.Competition.id == comp_id)) 
    return result.scalars().first() # 


# ---- Player CRUD ----
async def get_or_create_player(
    db: AsyncSession,
    competition_id: int,
    user_id: int,
    start_mmr: Optional[int] = None
) -> models.Player:
    """Получает участника соревнования или создает нового."""
    # Используем selectinload для жадной загрузки связанного объекта User
    result = await db.execute(
        select(models.Player)
        .options(selectinload(models.Player.user)) # <-- ВАЖНО
        .where(
            and_(
                models.Player.competition_id == competition_id,
                models.Player.user_id == user_id
            )
        )
    )
    player = result.scalars().first()

    if not player:
        if start_mmr is None:
            # Получаем соревнование для стартового MMR
            competition = await get_competition_by_id(db, competition_id) 
            if competition:
                start_mmr = competition.start_mmr
            else:
                start_mmr = 0

        player = models.Player(
            competition_id=competition_id,
            user_id=user_id,
            mmr=max(start_mmr, 0)
        )
        db.add(player)
        try:
            await db.commit() 
        except IntegrityError:
            await db.rollback() 
            result = await db.execute(
                select(models.Player)
                .options(selectinload(models.Player.user))
                .where(
                    and_(
                        models.Player.competition_id == competition_id,
                        models.Player.user_id == user_id
                    )
                )
            )
            player = result.scalars().first()
            if not player:
                 raise
    return player



async def update_player_stats_after_match( 
    db: AsyncSession, 
    competition_id: int, 
    user_id: int,
    mmr_delta: int, 
    is_winner: bool,
    achievements_gained: Optional[List[str]] = None 
) -> models.Player:
    """
    Обновляет полную статистику игрока после матча.
    """
    competition = await get_competition_by_id(db, competition_id) 
    if not competition:
        raise ValueError(f"Соревнование с ID {competition_id} не найдено.")

    player = await get_or_create_player(db, competition_id, user_id) 
    
    # Начинаем с базового изменения
    total_mmr_change = mmr_delta

    # Если игрок получил достижения от админа, добавляем их бонусы
    if achievements_gained:
        # Проходим по каждому полученному достижению
        for ach_name in achievements_gained:
            # Ищем это достижение в настройках соревнования
            # competition.achievements - это словарь {"НазваниеДостижения": bonus_mmr, ...}
            bonus_mmr = competition.achievements.get(ach_name, 0)
            total_mmr_change += bonus_mmr
            logger.debug(f"Начислен бонус MMR за достижение '{ach_name}': +{bonus_mmr}. Итого: {total_mmr_change}")

    # Применяем ИТОГОВОЕ изменение MMR к игроку
    player.mmr = max(player.mmr + total_mmr_change, 0)
    # ---------------------------------------------------------------

    # --- Остальная логика обновления статистики (wins, losses, streak) ---
    if is_winner:
        player.wins += 1
        if player.streak >= 0:
            player.streak += 1
        else:
            player.streak = 1 # Сброс серии поражений
    else:
        player.losses += 1
        if player.streak <= 0:
            player.streak -= 1
        else:
            player.streak = -1 # Сброс серии побед

    if achievements_gained:
        # 1. Получаем текущий словарь достижений игрока
        #    (Используем .copy() или dict() для создания копии, если он существует)
        current_achievements = player.achievements.copy() if player.achievements else {}
        
        # 2. Обновляем копию словаря
        for ach in achievements_gained:
            if ach in current_achievements:
                current_achievements[ach] += 1
            else:
                current_achievements[ach] = 1
        
        player.achievements = current_achievements

    await db.commit() 
    return player


async def create_match( 
    db: AsyncSession, 
    competition_id: int,
    winner_id: int,
    participants: List[Dict[str, Any]]
) -> models.Match:
    """
    Создает новый матч и записи участников.
    """
    match = models.Match(
        competition_id=competition_id,
        winner_id=winner_id,
        timestamp=int(time.time())
    )
    db.add(match)
    await db.commit() # <-- ASYNC CHANGE
    await db.refresh(match) # <-- ASYNC CHANGE

    created_participants = []
    for p_data in participants:
        mp = models.MatchParticipant(
            match_id=match.id,
            user_id=p_data["user_id"],
            mmr_change=p_data["mmr_change"],
            is_winner=p_data["is_winner"],
            achievements_gained=p_data.get("achievements", [])
        )
        db.add(mp)
        created_participants.append(mp)

        # --- Обновление статистики игрока ---
        await update_player_stats_after_match( # <-- ASYNC CHANGE
            db,
            competition_id=competition_id,
            user_id=p_data["user_id"],
            mmr_delta=p_data["mmr_change"],
            is_winner=p_data["is_winner"],
            achievements_gained=p_data.get("achievements", [])
        )

    await db.commit() 
    return match




async def get_competition_players(db: AsyncSession, competition_id: int) -> List[models.Player]: 
    """Получает список всех игроков в соревновании, отсортированных по MMR."""
    result = await db.execute(
        select(models.Player)
        .where(models.Player.competition_id == competition_id)
        .order_by(models.Player.mmr.desc())
        .options(selectinload(models.Player.user))
    )
    return list(result.scalars().all()) 


async def get_user_competitions(db: AsyncSession, user_id: int) -> List[models.Competition]: 
    """Получает список соревнований, в которых участвует пользователь."""
    result = await db.execute(
        select(models.Competition)
        .join(models.Player, models.Competition.id == models.Player.competition_id)
        .where(models.Player.user_id == user_id)
    )
    return list(result.scalars().all()) 


async def get_competition_by_chat_id(db: AsyncSession, chat_id: int) -> Optional[models.Competition]:
    """Получает соревнование по ID чата."""
    result = await db.execute(select(models.Competition).where(models.Competition.chat_id == chat_id))
    return result.scalars().first()



async def get_user_by_username(db: AsyncSession, username: str) -> Optional[models.User]:
    """Получает пользователя по его Telegram username."""
    if not username:
        return None
    
    result = await db.execute(select(models.User).where(models.User.username == username))
    return result.scalars().first()



async def get_administered_competitions(db: AsyncSession, user_id: int) -> List[models.Competition]:
    """
    Получает список соревнований, где пользователь является администратором
    (создатель или в списке admins).
    """
    logger.debug(f"Fetching administered competitions for user ID: {user_id}")
    try:
        stmt = select(models.Competition).where(
            models.Competition.creator_id == user_id
        )
        result = await db.execute(stmt)
        competitions = list(result.scalars().all())
        logger.debug(f"Found {len(competitions)} administered competitions for user {user_id}")
        return competitions
    except Exception as e:
        logger.error(f"Error fetching administered competitions for user {user_id}: {e}", exc_info=True)
        return [] 
    

    
async def get_competition_players(db: AsyncSession, competition_id: int) -> List[models.Player]:
    result = await db.execute(
        select(models.Player)
        .where(models.Player.competition_id == competition_id)
        .order_by(models.Player.mmr.desc())
        .options(selectinload(models.Player.user)) 
    )
    return list(result.scalars().all())


async def get_played_competitions(db: AsyncSession, user_id: int) -> List[models.Competition]:
    """
    Получает список соревнований, в которых участвует (играл) пользователь.
    """
    logger.debug(f"Fetching played competitions for user ID: {user_id}")
    try:
        stmt = (
            select(models.Competition)
            .join(models.Player) 
            .where(models.Player.user_id == user_id) 
        )
        result = await db.execute(stmt)
        competitions = list(result.scalars().all())
        logger.debug(f"Found {len(competitions)} played competitions for user {user_id}")
        return competitions
    except Exception as e:
        logger.error(f"Error fetching played competitions for user {user_id}: {e}", exc_info=True)
        return []
    

