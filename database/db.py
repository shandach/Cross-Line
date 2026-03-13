"""
Database operations for Client Counter
Локальная SQLite БД: entrance_logs, hourly_stats, line_config

НЕ отправляется в облако! Облако — только cloud_db.py
"""
import sys
from pathlib import Path
from datetime import date, datetime
from typing import List, Optional, Set

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, func, event
from sqlalchemy.orm import sessionmaker, Session as DBSession
from database.models import LocalBase, EntranceLog, HourlyStats, LineConfigRecord
from config import LOCAL_DB_PATH, LOCAL_DB_DIR, CAMERA_NAME, now_tashkent, today_tashkent


class Database:
    """SQLite local database manager"""
    
    def __init__(self):
        # Ensure data directory exists
        LOCAL_DB_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create engine with WAL mode
        self.engine = create_engine(
            f"sqlite:///{LOCAL_DB_PATH}",
            echo=False,
            connect_args={"check_same_thread": False}
        )
        
        # Enable WAL mode for concurrent access
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
        
        # Create tables
        LocalBase.metadata.create_all(self.engine)
        
        # Session factory
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def get_session(self) -> DBSession:
        """Get database session"""
        return self.SessionLocal()
    
    # ============ Entrance Log Operations ============
    
    def save_entrance(self, track_id: int, crossed_at: datetime = None) -> int:
        """
        Записать вход клиента (локальная БД).
        """
        if crossed_at is None:
            from config import naive_now_tashkent
            crossed_at = naive_now_tashkent()
        elif crossed_at.tzinfo is not None:
            crossed_at = crossed_at.replace(tzinfo=None)
        
        with self.get_session() as session:
            log = EntranceLog(
                track_id=track_id,
                crossed_at=crossed_at,
                log_date=crossed_at.date(),
                camera_name=CAMERA_NAME
            )
            session.add(log)
            session.commit()
            
            # Update hourly stats
            self._update_hourly_stats(session, crossed_at)
            
            return log.id
    
    def _update_hourly_stats(self, session: DBSession, crossed_at: datetime):
        """Update hourly statistics"""
        log_date = crossed_at.date()
        hour = crossed_at.hour
        
        stats = session.query(HourlyStats).filter(
            HourlyStats.log_date == log_date,
            HourlyStats.hour == hour,
            HourlyStats.camera_name == CAMERA_NAME
        ).first()
        
        if stats:
            stats.count += 1
        else:
            stats = HourlyStats(
                log_date=log_date,
                hour=hour,
                count=1,
                camera_name=CAMERA_NAME
            )
            session.add(stats)
        
        session.commit()
    
    def get_today_count(self) -> int:
        """Общее количество вошедших за сегодня (по Ташкенту)"""
        with self.get_session() as session:
            count = session.query(func.count(EntranceLog.id)).filter(
                EntranceLog.log_date == today_tashkent(),
                EntranceLog.camera_name == CAMERA_NAME
            ).scalar()
            return count or 0
    
    def get_count_for_date(self, target_date: date) -> int:
        """Количество за конкретную дату"""
        with self.get_session() as session:
            count = session.query(func.count(EntranceLog.id)).filter(
                EntranceLog.log_date == target_date,
                EntranceLog.camera_name == CAMERA_NAME
            ).scalar()
            return count or 0
    
    def get_hourly_breakdown(self, target_date: date = None) -> List[dict]:
        """Почасовая статистика"""
        if target_date is None:
            target_date = today_tashkent()
        
        with self.get_session() as session:
            stats = session.query(HourlyStats).filter(
                HourlyStats.log_date == target_date,
                HourlyStats.camera_name == CAMERA_NAME
            ).order_by(HourlyStats.hour).all()
            
            return [
                {'hour': s.hour, 'count': s.count}
                for s in stats
            ]
    
    def get_last_entrance_time(self) -> Optional[datetime]:
        """Время последнего входа сегодня"""
        with self.get_session() as session:
            log = session.query(EntranceLog).filter(
                EntranceLog.log_date == today_tashkent(),
                EntranceLog.camera_name == CAMERA_NAME
            ).order_by(EntranceLog.crossed_at.desc()).first()
            
            if log:
                return log.crossed_at
            return None
    
    def is_track_id_counted(self, track_id: int, target_date: date = None) -> bool:
        """Проверка: был ли этот track_id уже посчитан сегодня?"""
        if target_date is None:
            target_date = today_tashkent()
        
        with self.get_session() as session:
            count = session.query(func.count(EntranceLog.id)).filter(
                EntranceLog.track_id == track_id,
                EntranceLog.log_date == target_date,
                EntranceLog.camera_name == CAMERA_NAME
            ).scalar()
            return count > 0
    
    # ============ Line Config Operations (LOCAL ONLY) ============
    
    def save_line_config(self, line_start, line_end, direction='down'):
        """Сохранить конфиг линии в SQLite"""
        with self.get_session() as session:
            # Delete old config for this camera
            session.query(LineConfigRecord).filter(
                LineConfigRecord.camera_name == CAMERA_NAME
            ).delete()
            
            record = LineConfigRecord(
                line_start_x=line_start[0],
                line_start_y=line_start[1],
                line_end_x=line_end[0],
                line_end_y=line_end[1],
                direction=direction,
                camera_name=CAMERA_NAME,
                updated_at=now_tashkent()
            )
            session.add(record)
            session.commit()
            print(f"💾 Line saved to local DB: ({line_start}) → ({line_end})")
    
    def load_line_config_from_db(self) -> Optional[dict]:
        """Загрузить конфиг линии из SQLite"""
        try:
            with self.get_session() as session:
                record = session.query(LineConfigRecord).filter(
                    LineConfigRecord.camera_name == CAMERA_NAME
                ).order_by(LineConfigRecord.updated_at.desc()).first()
                
                if record:
                    return {
                        'line_start': (record.line_start_x, record.line_start_y),
                        'line_end': (record.line_end_x, record.line_end_y),
                        'direction': record.direction,
                    }
        except Exception as e:
            print(f"⚠️ Could not load line from DB: {e}")
        return None
    
    # ============ Employee Operations ============
    
    def get_employee_ids(self) -> Set[int]:
        """Получить ID сотрудников (если таблица есть)"""
        try:
            from sqlalchemy import text
            with self.get_session() as session:
                result = session.execute(
                    text("SELECT id FROM employees WHERE is_active = 1")
                )
                return {row[0] for row in result}
        except Exception:
            return set()
    
    def get_employee_names(self) -> dict:
        """Get employee id -> name mapping"""
        try:
            from sqlalchemy import text
            with self.get_session() as session:
                result = session.execute(
                    text("SELECT id, name FROM employees WHERE is_active = 1")
                )
                return {row[0]: row[1] for row in result}
        except Exception:
            return {}


# Global database instance
db = Database()
