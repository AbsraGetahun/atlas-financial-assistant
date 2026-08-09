from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from config import DB_URL

Base = declarative_base()
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DB_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)  # Telegram user ID
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    role = Column(String, nullable=True)           # Investor, Analyst, Founder, etc.
    interests = Column(Text, nullable=True)        # comma-separated topics/sectors
    briefing_time = Column(String, default="08:00")
    evening_summary = Column(Boolean, default=True)  # opt-in evening summary
    onboarded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    watchlist = relationship("WatchlistItem", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("MessageLog", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("PriceAlert", back_populates="user", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticker = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="watchlist")


class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticker = Column(String, index=True)
    condition = Column(String)   # "above" | "below" | "change_pct"
    threshold = Column(Float)    # price level or % move
    triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="alerts")


class MessageLog(Base):
    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role = Column(String)   # "user" or "model"
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="messages")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
