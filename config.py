"""
Client Counter Configuration
Подсчёт входящих клиентов банка
"""
import os
import json
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
import pytz

# Load environment variables
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# Force TCP transport for RTSP
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# ═══════════════════════════════════════════════════
# Timezone — Ташкент (UTC+5)
# ═══════════════════════════════════════════════════
TZ_TASHKENT = pytz.timezone("Asia/Tashkent")


def now_tashkent() -> datetime:
    """Текущее время по Ташкенту"""
    return datetime.now(TZ_TASHKENT)


def today_tashkent():
    """Текущая дата по Ташкенту"""
    return now_tashkent().date()


# ═══════════════════════════════════════════════════
# Branch & Camera (для масштабирования на филиалы)
# ═══════════════════════════════════════════════════
BRANCH_ID = os.getenv("BRANCH_ID", "branch_01")
BRANCH_NAME = os.getenv("BRANCH_NAME", "Главный офис")
CAMERA_URL = os.getenv("CAMERA_URL", "0")
CAMERA_NAME = os.getenv("CAMERA_NAME", "Entrance Camera")

# Уникальный ID камеры (branch + camera) — для облака
CAMERA_ID = f"{BRANCH_ID}_{CAMERA_NAME}".replace(" ", "_").lower()

# ═══════════════════════════════════════════════════
# Database — Local SQLite (line config, local stats)
# ═══════════════════════════════════════════════════
LOCAL_DB_DIR = BASE_DIR / "data"
LOCAL_DB_PATH = LOCAL_DB_DIR / "local.db"

# ═══════════════════════════════════════════════════
# Cloud PostgreSQL (Railway) — only crossing data
# ═══════════════════════════════════════════════════
CLOUD_DB_DSN = os.getenv("DB_DSN", "")

# ═══════════════════════════════════════════════════
# Work Shift (Tashkent, UTC+5)
# ═══════════════════════════════════════════════════
WORK_START = os.getenv("WORK_START", "00:00")
WORK_END = os.getenv("WORK_END", "23:59")

# ═══════════════════════════════════════════════════
# AI Settings
# ═══════════════════════════════════════════════════
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")  # Nano model is best for CPU
DETECTION_CONFIDENCE = float(os.getenv("DETECTION_CONFIDENCE", "0.5"))

# Filter out non-human shapes
PERSON_MIN_ASPECT_RATIO = 1.2
PERSON_MAX_WIDTH_RATIO = 0.6
PERSON_CLASS_ID = 0  # COCO class 0 = person

# ═══════════════════════════════════════════════════
# Tracking Logic (bottom, center, top)
# ═══════════════════════════════════════════════════
TRACKING_ANCHOR = os.getenv("TRACKING_ANCHOR", "bottom").lower()

# ═══════════════════════════════════════════════════
# Frame Settings
# ═══════════════════════════════════════════════════
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "1920"))
FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "1080"))

# ═══════════════════════════════════════════════════
# Display
# ═══════════════════════════════════════════════════
WINDOW_NAME = "Client Counter"
FULLSCREEN_MODE = os.getenv("FULLSCREEN_MODE", "false").lower() == "true"

# Colors (BGR)
LINE_COLOR = (0, 0, 255)          # Red — counting line
ROI_COLOR = (255, 200, 0)         # Cyan — ROI zone
ROI_FILL_ALPHA = 0.15
COUNTED_COLOR = (0, 255, 0)       # Green — counted person
TRACKING_COLOR = (255, 0, 255)    # Magenta — tracked person
TEXT_COLOR = (255, 255, 255)
STATS_BG_COLOR = (30, 30, 30)

# ═══════════════════════════════════════════════════
# Counting Line (saved to/loaded from line_config.json)
# ═══════════════════════════════════════════════════
LINE_CONFIG_PATH = BASE_DIR / "line_config.json"


def load_line_config():
    """Load line configuration from JSON file"""
    if LINE_CONFIG_PATH.exists():
        try:
            with open(LINE_CONFIG_PATH, 'r') as f:
                data = json.load(f)
            return {
                'line_start': tuple(data['line_start']),
                'line_end': tuple(data['line_end']),
                'direction': data.get('direction', 'down'),
            }
        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️ Failed to load line config: {e}")
    return None


def save_line_config(line_start, line_end, direction='down'):
    """Save line configuration to JSON file"""
    data = {
        'line_start': list(line_start),
        'line_end': list(line_end),
        'direction': direction,
    }
    with open(LINE_CONFIG_PATH, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✅ Line config saved: {line_start} → {line_end} (direction: {direction})")
    
    # Also save to local SQLite
    try:
        from database.db import db
        db.save_line_config(line_start, line_end, direction)
    except Exception as e:
        print(f"⚠️ Could not save to local DB: {e}")


def delete_line_config():
    """Delete line configuration file"""
    if LINE_CONFIG_PATH.exists():
        LINE_CONFIG_PATH.unlink()
        print("🗑️ Line config deleted")


def print_config():
    """Print current configuration"""
    print("\n" + "=" * 50)
    print("🏦 CLIENT COUNTER CONFIGURATION")
    print("=" * 50)
    print(f"  Branch: {BRANCH_NAME} ({BRANCH_ID})")
    print(f"  Camera: {CAMERA_NAME} (ID: {CAMERA_ID})")
    
    display_url = CAMERA_URL
    if 'rtsp://' in str(CAMERA_URL):
        import re
        display_url = re.sub(r'://[^:]+:[^@]+@', '://***:***@', str(CAMERA_URL))
    print(f"  URL: {display_url}")
    
    print(f"  Shift: {WORK_START} – {WORK_END} (Tashkent, UTC+5)")
    print(f"  Local DB: {LOCAL_DB_PATH}")
    print(f"  Cloud DB: {'✅ Connected' if CLOUD_DB_DSN else '❌ Not configured'}")
    print(f"  YOLO: {YOLO_MODEL} (conf={DETECTION_CONFIDENCE})")
    print(f"  Anchor: {TRACKING_ANCHOR.upper()} (Tracking Point)")
    print(f"  Time now: {now_tashkent().strftime('%Y-%m-%d %H:%M:%S')} (Tashkent)")
    
    line_cfg = load_line_config()
    if line_cfg:
        print(f"  Line: {line_cfg['line_start']} → {line_cfg['line_end']} (IN: {line_cfg['direction']})")
    else:
        print("  Line: NOT CONFIGURED (will draw on startup)")
    
    print("=" * 50 + "\n")


if __name__ == "__main__":
    print_config()
