"""
REST API for Client Counter — для будущего подключения к веб-UI

Минимальный API на FastAPI:
- GET /api/today — статистика за сегодня
- GET /api/date/{date} — статистика за конкретную дату
- Только localhost — данные не передаются наружу
"""
import sys
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent))

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

from database.db import db
from config import CAMERA_NAME, WORK_START, WORK_END


def create_app():
    """Create FastAPI application"""
    if not HAS_FASTAPI:
        print("❌ FastAPI not installed. Run: pip install fastapi uvicorn")
        return None
    
    app = FastAPI(
        title="Bank Client Counter API",
        description="Подсчёт входящих клиентов банка",
        version="1.0.0"
    )
    
    # CORS — только для localhost
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    
    @app.get("/api/today")
    def get_today():
        """Статистика за сегодня"""
        today = date.today()
        return {
            "date": today.isoformat(),
            "camera": CAMERA_NAME,
            "shift": f"{WORK_START}-{WORK_END}",
            "total_count": db.get_today_count(),
            "hourly": db.get_hourly_breakdown(today),
            "last_entry": str(db.get_last_entrance_time() or ""),
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/api/date/{target_date}")
    def get_by_date(target_date: str):
        """Статистика за конкретную дату"""
        try:
            d = date.fromisoformat(target_date)
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}
        
        return {
            "date": d.isoformat(),
            "camera": CAMERA_NAME,
            "shift": f"{WORK_START}-{WORK_END}",
            "total_count": db.get_count_for_date(d),
            "hourly": db.get_hourly_breakdown(d),
            "timestamp": datetime.now().isoformat()
        }
    
    @app.get("/api/health")
    def health():
        """Health check"""
        return {"status": "ok", "camera": CAMERA_NAME}
    
    return app


if __name__ == "__main__":
    app = create_app()
    if app:
        print("🌐 Starting API server on http://localhost:8100")
        print("   Endpoints: /api/today, /api/date/{date}, /api/health")
        uvicorn.run(app, host="127.0.0.1", port=8100, log_level="info")
    else:
        print("Install FastAPI: pip install fastapi uvicorn")
