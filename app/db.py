from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy import Integer, String, Boolean, Date, DateTime, ForeignKey
from sqlalchemy.types import JSON
from datetime import datetime


DATABASE_URL = "sqlite:///./golf_sim_stats.db"


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)

    round_players: Mapped[list["RoundPlayer"]] = relationship(back_populates="player")


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    course_name: Mapped[str | None] = mapped_column(String, nullable=True)
    tee_set: Mapped[str | None] = mapped_column(String, nullable=True)
    is_team_round: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    hole_pars: Mapped[list | None] = mapped_column(JSON, nullable=True)
    stroke_indexes: Mapped[list | None] = mapped_column(JSON, nullable=True)

    round_players: Mapped[list["RoundPlayer"]] = relationship(back_populates="round")


class RoundPlayer(Base):
    __tablename__ = "round_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_name: Mapped[str | None] = mapped_column(String, nullable=True)

    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    out_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    in_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    fairways_hit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fairways_possible: Mapped[int | None] = mapped_column(Integer, nullable=True)

    gir: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gir_possible: Mapped[int | None] = mapped_column(Integer, nullable=True)

    avg_drive_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_putts: Mapped[int | None] = mapped_column(Integer, nullable=True)

    scramble_successes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scramble_opportunities: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sand_save_successes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sand_save_opportunities: Mapped[int | None] = mapped_column(Integer, nullable=True)

    round: Mapped["Round"] = relationship(back_populates="round_players")
    player: Mapped["Player"] = relationship(back_populates="round_players")
    hole_scores: Mapped[list["HoleScore"]] = relationship(back_populates="round_player")


class HoleScore(Base):
    __tablename__ = "hole_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    round_player_id: Mapped[int] = mapped_column(ForeignKey("round_players.id"))
    hole_number: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)

    round_player: Mapped["RoundPlayer"] = relationship(back_populates="hole_scores")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT hole_pars FROM rounds LIMIT 1"))
    except Exception:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE rounds ADD COLUMN hole_pars TEXT"))
            conn.execute(text("ALTER TABLE rounds ADD COLUMN stroke_indexes TEXT"))
            conn.commit()

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT out_score, in_score FROM round_players LIMIT 1"))
    except Exception:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE round_players ADD COLUMN out_score INTEGER"))
            conn.execute(text("ALTER TABLE round_players ADD COLUMN in_score INTEGER"))
            conn.commit()

