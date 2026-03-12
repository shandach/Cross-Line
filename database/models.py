"""
Database models for Client Counter

Две группы моделей:
1. LocalBase — SQLite (линия, локальная статистика) — НЕ отправляется в облако
2. CloudBase — PostgreSQL (данные о клиентах) — отправляется в Railway
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, Date, Float, Text
from sqlalchemy.orm import declarative_base

# === Local SQLite models ===
LocalBase = declarative_base()


class EntranceLog(LocalBase):
    """Лог входа каждого клиента (локальная копия)"""
    __tablename__ = "entrance_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(Integer, nullable=False)
    crossed_at = Column(DateTime, nullable=False)
    log_date = Column(Date, nullable=False)
    camera_name = Column(String(200), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<EntranceLog(id={self.id}, track_id={self.track_id}, crossed_at={self.crossed_at})>"


class HourlyStats(LocalBase):
    """Почасовая статистика (локальная)"""
    __tablename__ = "entrance_hourly_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    log_date = Column(Date, nullable=False)
    hour = Column(Integer, nullable=False)
    count = Column(Integer, default=0)
    camera_name = Column(String(200), default="")
    
    def __repr__(self):
        return f"<HourlyStats(date={self.log_date}, hour={self.hour}, count={self.count})>"


class LineConfigRecord(LocalBase):
    """Конфигурация линии (только локально!)"""
    __tablename__ = "line_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    line_start_x = Column(Integer, nullable=False)
    line_start_y = Column(Integer, nullable=False)
    line_end_x = Column(Integer, nullable=False)
    line_end_y = Column(Integer, nullable=False)
    direction = Column(String(20), default="down")
    camera_name = Column(String(200), default="")
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return (f"<LineConfig(({self.line_start_x},{self.line_start_y}) → "
                f"({self.line_end_x},{self.line_end_y}), dir={self.direction})>")


# === Cloud PostgreSQL models ===
CloudBase = declarative_base()


class ClientCrossing(CloudBase):
    """
    Пересечение линии клиентом — отправляется в облако (Railway PostgreSQL)
    
    Это единственная таблица в облаке. 
    Линия, настройки, локальная статистика — НЕ отправляются.
    
    Масштабирование: branch_id + camera_name = уникальная камера
    """
    __tablename__ = "client_crossings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    branch_id = Column(String(100), nullable=False)       # ID филиала (branch_01, branch_02...)
    branch_name = Column(String(200), default="")         # Название филиала
    camera_name = Column(String(200), default="")         # Имя камеры
    track_id = Column(Integer, nullable=False)             # ByteTrack ID
    crossed_at = Column(DateTime, nullable=False)          # Время по Ташкенту
    log_date = Column(Date, nullable=False)                # Дата (для группировки)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ClientCrossing(branch={self.branch_id}, track={self.track_id}, at={self.crossed_at})>"
