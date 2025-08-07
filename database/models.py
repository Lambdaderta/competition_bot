from sqlalchemy import (
    Column, Integer, String, Boolean, JSON, ForeignKey,
    CheckConstraint, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    """
    Модель пользователя системы.
    Хранит информацию о пользователе Telegram.
    """
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)  # Внутренний уникальный ID пользователя в системе
    user_id = Column(Integer, unique=True, nullable=False, index=True)  # Уникальный Telegram ID пользователя
    username = Column(String)  # Текущий @username пользователя в Telegram (может меняться)
    full_name = Column(String)  # Полное имя пользователя из Telegram


class Competition(Base):
    """
    Модель соревнования.
    Определяет отдельное соревнование с настройками рейтинга и правилами.
    """
    __tablename__ = 'competitions'
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    # --- НОВОЕ ПОЛЕ ---
    chat_id = Column(Integer, nullable=False, index=True) 
    # ------------------
    creator_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    start_mmr = Column(Integer, default=0, nullable=False)
    use_formula = Column(Boolean, default=False)
    formula = Column(String) 
    range_rules = Column(JSON)
    ranks = Column(JSON)
    achievements = Column(JSON) 
    admins = Column(JSON, default=list) # [user_id1, user_id2]

    creator = relationship("User")
    players = relationship("Player", cascade="all, delete-orphan")
    matches = relationship("Match", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_competitions_chat', 'chat_id'),
    )

class Player(Base):
    """
    Модель участника соревнования.
    Хранит статистику конкретного пользователя в конкретном соревновании.
    """
    __tablename__ = 'players'
    __table_args__ = (
        CheckConstraint('mmr >= 0', name='mmr_non_negative'),  # MMR не может быть отрицательным
        UniqueConstraint('competition_id', 'user_id', name='uq_player_comp_user'),  # Уникальность участия пользователя в соревновании
        Index('idx_players_competition', 'competition_id'),  # Индекс для поиска игроков по соревнованию
        Index('idx_players_user', 'user_id'),  # Индекс для поиска соревнований пользователя
    )
    id = Column(Integer, primary_key=True)  # Внутренний уникальный ID записи участника
    competition_id = Column(Integer, ForeignKey('competitions.id'), nullable=False)  # ID соревнования (ссылка на Competition.id)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)  # ID пользователя (ссылка на User.id)
    mmr = Column(Integer, default=0, nullable=False)  # Текущий рейтинг MMR участника в соревновании
    wins = Column(Integer, default=0)  # Общее количество побед
    losses = Column(Integer, default=0)  # Общее количество поражений
    streak = Column(Integer, default=0)  # Текущая серия (положительная - победы, отрицательная - поражения)
    # Полученные достижения и их количество для этого участника в этом соревновании.
    achievements = Column(JSON, default=dict)

    # Отношения SQLAlchemy
    user = relationship("User")  # Связь с объектом User
    competition = relationship("Competition")  # Связь с объектом Competition

class Match(Base):
    """
    Модель матча.
    Представляет один сыгранный матч в рамках соревнования.
    """
    __tablename__ = 'matches'
    __table_args__ = (
        Index('idx_matches_competition', 'competition_id'),  # Индекс для поиска матчей по соревнованию
        Index('idx_matches_timestamp', 'timestamp'),  # Индекс для сортировки/фильтрации по времени
    )
    id = Column(Integer, primary_key=True)  # Внутренний уникальный ID матча
    competition_id = Column(Integer, ForeignKey('competitions.id'), nullable=False)  # ID соревнования (ссылка на Competition.id)
    winner_id = Column(Integer, ForeignKey('users.id'), nullable=False)  # ID победителя матча (ссылка на User.id)
    timestamp = Column(Integer, nullable=False)  # Время проведения матча (Unix timestamp)

    # Отношения SQLAlchemy
    competition = relationship("Competition")  # Связь с объектом Competition
    winner = relationship("User")  # Связь с объектом User победителя
    # Связь с участниками матча. При удалении матча удаляются все связанные записи MatchParticipant.
    participants = relationship("MatchParticipant", cascade="all, delete-orphan")

class MatchParticipant(Base):
    """
    Модель участника конкретного матча.
    Хранит результаты и изменения для каждого игрока в матче.
    """
    __tablename__ = 'match_participants'
    __table_args__ = (
        Index('idx_match_participants_match', 'match_id'),  # Индекс для поиска участников по матчу
        Index('idx_match_participants_user', 'user_id'),  # Индекс для поиска матчей пользователя
    )
    id = Column(Integer, primary_key=True)  # Внутренний уникальный ID записи участника матча
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=False)  # ID матча (ссылка на Match.id)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)  # ID пользователя (ссылка на User.id)
    mmr_change = Column(Integer, nullable=False)  # Изменение MMR пользователя в результате этого матча
    is_winner = Column(Boolean, nullable=False)  # Флаг: был ли пользователь победителем в этом матче
    # Список достижений, полученных пользователем в этом конкретном матче.
    # Пример: ["Победитель дня", "Первая победа"]
    achievements_gained = Column(JSON, default=list)

    # Отношения SQLAlchemy
    match = relationship("Match")  # Связь с объектом Match
    user = relationship("User")  # Связь с объектом User