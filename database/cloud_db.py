"""
Cloud Database — Railway PostgreSQL

Только для отправки данных о пересечении линии клиентами.
Линия, настройки, локальная статистика — НЕ отправляются.

Автоматический retry при потере связи.
"""
import sys
import threading
import logging
from pathlib import Path
from datetime import datetime, date
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session as DBSession
from database.models import CloudBase, ClientCrossing
from config import CLOUD_DB_DSN, CAMERA_NAME, BRANCH_ID, BRANCH_NAME, now_tashkent

logger = logging.getLogger("cloud_db")


class CloudDatabase:
    """
    PostgreSQL (Railway) — только данные о клиентах.
    
    Работает в фоновом потоке для минимизации задержки.
    При ошибке подключения — пропускает, не крашит систему.
    """
    
    def __init__(self):
        self.engine = None
        self.SessionLocal = None
        self.connected = False
        self._lock = threading.Lock()
        
        if not CLOUD_DB_DSN:
            print("☁️ Cloud DB: NOT CONFIGURED (DB_DSN empty)")
            return
        
        try:
            self.engine = create_engine(
                CLOUD_DB_DSN,
                echo=False,
                pool_size=3,
                max_overflow=5,
                pool_timeout=10,
                pool_recycle=1800,  # Reconnect every 30 min
                pool_pre_ping=True,  # Auto-detect broken connections
            )
            
            # Create tables if not exist
            CloudBase.metadata.create_all(self.engine)
            
            self.SessionLocal = sessionmaker(bind=self.engine)
            self.connected = True
            print("☁️ Cloud DB: ✅ Connected to Railway PostgreSQL")
            
        except Exception as e:
            print(f"☁️ Cloud DB: ❌ Connection failed: {e}")
            print("   System will continue without cloud sync")
            self.connected = False
    
    def get_session(self) -> Optional[DBSession]:
        """Get database session (returns None if not connected)"""
        if not self.connected or self.SessionLocal is None:
            return None
        try:
            return self.SessionLocal()
        except Exception as e:
            logger.error(f"Cloud DB session error: {e}")
            return None
    
    def push_crossing(self, track_id: int, crossed_at: datetime = None):
        """
        Отправить данные о пересечении в облако.
        
        Вызывается в фоновом потоке для минимизации задержки основного цикла.
        """
        if not self.connected:
            return
        
        if crossed_at is None:
            crossed_at = now_tashkent()
        
        def _push():
            try:
                session = self.get_session()
                if session is None:
                    return
                
                with session:
                    crossing = ClientCrossing(
                        branch_id=BRANCH_ID,
                        branch_name=BRANCH_NAME,
                        camera_name=CAMERA_NAME,
                        track_id=track_id,
                        crossed_at=crossed_at,
                        log_date=crossed_at.date(),
                    )
                    session.add(crossing)
                    session.commit()
                    logger.info(f"☁️ Pushed crossing: track={track_id}, at={crossed_at}")
                    
            except Exception as e:
                logger.error(f"☁️ Cloud push failed: {e}")
                # Don't crash — local data is still saved
        
        # Run in background thread
        thread = threading.Thread(target=_push, daemon=True)
        thread.start()
    
    def get_today_count_cloud(self) -> int:
        """Получить количество пересечений за сегодня из облака"""
        if not self.connected:
            return 0
        
        try:
            from sqlalchemy import func
            session = self.get_session()
            if session is None:
                return 0
            
            with session:
                today = now_tashkent().date()
                count = session.query(func.count(ClientCrossing.id)).filter(
                    ClientCrossing.log_date == today,
                    ClientCrossing.camera_name == CAMERA_NAME
                ).scalar()
                return count or 0
                
        except Exception as e:
            logger.error(f"Cloud count query failed: {e}")
            return 0
    
    def test_connection(self) -> bool:
        """Проверить подключение к облаку"""
        if not self.connected:
            return False
        
        try:
            session = self.get_session()
            if session is None:
                return False
            
            with session:
                session.execute(CloudBase.metadata.tables['client_crossings'].select().limit(1))
                return True
                
        except Exception as e:
            logger.error(f"Cloud connection test failed: {e}")
            return False


# Global cloud database instance
cloud_db = CloudDatabase()
