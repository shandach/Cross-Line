"""
Client Counter — Подсчёт входящих клиентов банка

Основной скрипт:
- RTSP камера → YOLO + ByteTrack → пересечение линии
- Данные → SQLite (локально) + PostgreSQL (облако Railway)
- Q = сохранить линию (при рисовании) / выйти (при работе)
- Автозагрузка линии из line_config.json
- Рабочая смена 08:45 – 18:15 (Ташкент, UTC+5)
"""
import cv2
import sys
import time
import numpy as np
from datetime import datetime, date
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    CAMERA_URL, CAMERA_NAME, WORK_START, WORK_END,
    WINDOW_NAME, FULLSCREEN_MODE, FRAME_WIDTH, FRAME_HEIGHT,
    LINE_COLOR, ROI_FILL_ALPHA,
    load_line_config, save_line_config, delete_line_config, print_config,
    now_tashkent, today_tashkent
)
from core.stream_handler import StreamHandler
from core.detector import TrackingDetector
from core.line_crossing_engine import LineCrossingEngine
from database.db import db
from database.cloud_db import cloud_db
from gui.display import (
    draw_counting_line, draw_direction_arrow,
    draw_stats_table, draw_big_counter, draw_shift_status,
    draw_line_setup_mode
)


class ClientCounter:
    """Главное приложение подсчёта клиентов"""
    
    def __init__(self):
        print("\n🏦 CLIENT COUNTER SYSTEM")
        print("=" * 50)
        print_config()
        
        # Stream handler
        self.stream = StreamHandler()
        
        # YOLO + ByteTrack detector
        print("[INFO] Loading YOLO + ByteTrack...")
        self.detector = TrackingDetector()
        
        # Line crossing engine (создаётся после настройки линии)
        self.engine = None
        
        # Line setup state
        self.line_config = load_line_config()
        self.setup_mode = False
        self.setup_points = []
        self.mouse_pos = (0, 0)
        
        # UI state
        self.running = False
        self.is_fullscreen = FULLSCREEN_MODE
        self.show_detections = True
        
        # Shift tracking
        self.shift_active = False
        self.shift_reset_done_today = False
        self.last_shift_check = 0
        
        # Stats cache
        self._stats_cache = {'count': 0, 'hourly': [], 'last_time': None}
        self._last_stats_update = 0
        self._stats_update_interval = 1.0
        
        # Initialize engine if config exists
        if self.line_config:
            self._create_engine()
            print(f"✅ Line loaded: {self.line_config['line_start']} → {self.line_config['line_end']}")
        else:
            print("⚠️ Line not configured. Will enter draw mode on startup.")
    
    def _create_engine(self):
        """Создать движок подсчёта из конфига"""
        if self.line_config:
            self.engine = LineCrossingEngine(
                line_start=self.line_config['line_start'],
                line_end=self.line_config['line_end'],
                direction=self.line_config.get('direction', 'down')
            )
    
    def _is_shift_time(self) -> bool:
        """Проверить: сейчас рабочая смена? (по Ташкенту, ПН-ПТ)"""
        now = now_tashkent()
        
        # Выходные (5 = Суббота, 6 = Воскресенье)
        if now.weekday() >= 5:
            return False
            
        start_h, start_m = map(int, WORK_START.split(":"))
        end_h, end_m = map(int, WORK_END.split(":"))
        
        shift_start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        shift_end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        
        return shift_start <= now <= shift_end
    
    def _check_shift_boundaries(self):
        """Проверить границы смены (сброс в 18:15)"""
        now = time.time()
        if now - self.last_shift_check < 30:
            return
        self.last_shift_check = now
        
        is_shift = self._is_shift_time()
        
        if is_shift and not self.shift_active:
            self.shift_active = True
            self.shift_reset_done_today = False
            print(f"🟢 Shift started: {WORK_START} (Tashkent)")
            
            if self.engine:
                self.engine.reset_shift()
                self.detector.reset_tracker()
            
            self._reload_count_from_db()
        
        elif not is_shift and self.shift_active:
            self.shift_active = False
            
            if not self.shift_reset_done_today:
                self.shift_reset_done_today = True
                print(f"🔴 Shift ended: {WORK_END} (Tashkent)")
                print(f"   Total today: {self.engine.total_count if self.engine else 0}")
                
                if self.engine:
                    self.engine.reset_shift()
                    self.detector.reset_tracker()
    
    def _reload_count_from_db(self):
        """Перезагрузить счёт из БД"""
        if self.engine:
            db_count = db.get_today_count()
            if db_count > 0:
                self.engine.total_count = db_count
                print(f"📊 Restored count from DB: {db_count}")
    
    def _update_stats_cache(self):
        """Обновить кэш статистики"""
        now = time.time()
        if now - self._last_stats_update < self._stats_update_interval:
            return
        self._last_stats_update = now
        
        self._stats_cache = {
            'count': self.engine.total_count if self.engine else 0,
            'hourly': db.get_hourly_breakdown(),
            'last_time': db.get_last_entrance_time()
        }
    
    def _handle_mouse(self, event, x, y, flags, param):
        """Обработка мыши"""
        self.mouse_pos = (x, y)
        
        if self.setup_mode and event == cv2.EVENT_LBUTTONDOWN:
            self.setup_points.append((x, y))
            print(f"📍 Point {len(self.setup_points)}: ({x}, {y})")
    
    def _save_and_activate_line(self):
        """Сохранить линию и активировать счётчик"""
        if len(self.setup_points) < 2:
            return False
        
        # Save to JSON file + local SQLite
        save_line_config(
            self.setup_points[0],
            self.setup_points[1],
            direction='down'
        )
        self.line_config = load_line_config()
        self._create_engine()
        self._reload_count_from_db()
        self.setup_mode = False
        self.setup_points = []
        print("✅ Line saved and activated! Counting started.")
        return True
    
    def _handle_keyboard(self):
        """Обработка клавиатуры"""
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q') or key == ord('Q'):
            if self.setup_mode and len(self.setup_points) >= 2:
                # Q во время рисования = СОХРАНИТЬ линию
                self._save_and_activate_line()
            elif self.setup_mode:
                # Q без 2 точек = отмена
                print("❌ Need 2 points! Click start and end of counting line.")
            else:
                # Q в рабочем режиме = выход
                self.running = False
        
        elif key == ord('l') or key == ord('L'):
            if not self.setup_mode:
                self.setup_mode = True
                self.setup_points = []
                print("📏 LINE SETUP MODE: Click 2 points to draw counting line, then press Q")
            else:
                self.setup_mode = False
                self.setup_points = []
                print("❌ Line setup cancelled")
        
        elif key == 13:  # Enter — also saves line
            if self.setup_mode and len(self.setup_points) >= 2:
                self._save_and_activate_line()
        
        elif key == 27:  # Escape
            if self.setup_mode:
                self.setup_mode = False
                self.setup_points = []
                print("❌ Line setup cancelled")
        
        elif key == ord('d') or key == ord('D'):
            if self.engine and self.line_config:
                directions = ['down', 'up', 'left', 'right']
                current = self.line_config.get('direction', 'down')
                idx = directions.index(current)
                new_dir = directions[(idx + 1) % len(directions)]
                
                save_line_config(
                    self.line_config['line_start'],
                    self.line_config['line_end'],
                    direction=new_dir
                )
                self.line_config = load_line_config()
                self._create_engine()
                self._reload_count_from_db()
                print(f"🔄 Direction changed to: {new_dir}")
        
        elif key == ord('f') or key == ord('F'):
            self.is_fullscreen = not self.is_fullscreen
            if self.is_fullscreen:
                cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            else:
                cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        
        elif key == ord('b') or key == ord('B'):
            self.show_detections = not self.show_detections
        
        elif key == ord('r') or key == ord('R'):
            if self.engine:
                self.engine.reset_shift()
                self.detector.reset_tracker()
                print("🔄 Manual reset done")
        
        elif key == ord('h') or key == ord('H'):
            print("\n" + "=" * 50)
            print("📋 KEYBOARD SHORTCUTS:")
            print("  L — Draw counting line (2 points)")
            print("  Q — Save line (in draw mode) / Quit (in work mode)")
            print("  D — Change IN direction (down/up/left/right)")
            print("  B — Toggle detection boxes")
            print("  F — Toggle fullscreen")
            print("  R — Reset counters")
            print("  H — Show this help")
            print("  Enter — Also saves line in draw mode")
            print("  Esc — Cancel line drawing")
            print("=" * 50 + "\n")
    
    def run(self):
        """Главный цикл"""
        # Start stream
        print("[INFO] Connecting to camera...")
        if not self.stream.start():
            print("❌ Failed to connect to camera!")
            print(f"   URL: {CAMERA_URL}")
            print("   Check .env CAMERA_URL setting")
            return
        
        # Create window
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        if self.is_fullscreen:
            cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.setMouseCallback(WINDOW_NAME, self._handle_mouse)
        
        self.running = True
        self.last_shift_check = 0
        
        # If no line config — enter draw mode automatically
        if not self.line_config:
            self.setup_mode = True
            self.setup_points = []
            print("\n📏 No counting line found! Draw it now:")
            print("   1. Click 2 points across the entrance")
            print("   2. Press Q to save (or Enter)")
            print()
        else:
            # Reload count from DB
            if self.engine:
                self._reload_count_from_db()
        
        print("\n🟢 Client Counter started! Press H for help\n")
        
        fps_time = time.time()
        frame_count = 0
        fps = 0
        
        try:
            while self.running:
                # Read frame
                ret, frame = self.stream.read_frame()
                if not ret or frame is None:
                    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                    cv2.putText(frame, "No Signal / Reconnecting...", (400, 360),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
                    cv2.imshow(WINDOW_NAME, frame)
                    self._handle_keyboard()
                    continue
                
                # Check shift boundaries
                self._check_shift_boundaries()
                
                # === LINE SETUP MODE ===
                if self.setup_mode:
                    frame = draw_line_setup_mode(frame, self.setup_points, self.mouse_pos)
                    
                    cv2.imshow(WINDOW_NAME, frame)
                    self._handle_keyboard()
                    continue
                
                # === COUNTING MODE ===
                if self.engine:
                    # Run YOLO + ByteTrack
                    detections = self.detector.detect(frame)
                    
                    # Update zone counting engine
                    new_crossings = self.engine.update(detections)
                    
                    # Save new crossings to LOCAL DB + CLOUD
                    crossed_at = now_tashkent()
                    for track_id in new_crossings:
                        # 1. Local SQLite
                        db.save_entrance(track_id, crossed_at)
                        
                        # 2. Cloud PostgreSQL (Railway) — async
                        cloud_db.push_crossing(track_id, crossed_at)
                    
                    # Update stats cache
                    self._update_stats_cache()
                    
                    # === DRAW OVERLAYS ===
                    
                    # Counting Line
                    frame = draw_counting_line(
                        frame, 
                        self.line_config['line_start'], 
                        self.line_config['line_end'], 
                        LINE_COLOR, 3
                    )
                    
                    # Direction arrow
                    direction = self.line_config.get('direction', 'down')
                    frame = draw_direction_arrow(
                        frame, 
                        self.line_config['line_start'], 
                        self.line_config['line_end'], 
                        direction
                    )
                    
                    # Person detections
                    if self.show_detections:
                        frame = self.detector.draw_detections(
                            frame, detections, self.engine.counted_ids
                        )
                    
                    # Big counter
                    frame = draw_big_counter(frame, self._stats_cache['count'])
                    
                    # Stats table
                    frame = draw_stats_table(
                        frame,
                        total_count=self._stats_cache['count'],
                        hourly_data=self._stats_cache['hourly'],
                        last_entry_time=self._stats_cache['last_time'],
                        work_start=WORK_START,
                        work_end=WORK_END
                    )
                    
                    # Shift status
                    frame = draw_shift_status(frame, WORK_START, WORK_END, self._is_shift_time())
                    
                    # Cloud status indicator
                    cloud_status = "CLOUD: ON" if cloud_db.connected else "CLOUD: OFF"
                    cloud_color = (0, 255, 0) if cloud_db.connected else (0, 0, 255)
                    h_f, w_f = frame.shape[:2]
                    cv2.putText(frame, cloud_status, (w_f - 160, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, cloud_color, 1)
                
                else:
                    # No line configured
                    cv2.putText(frame, "Press L to draw counting line", (50, 50),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                
                # FPS counter
                frame_count += 1
                elapsed = time.time() - fps_time
                if elapsed >= 1.0:
                    fps = frame_count / elapsed
                    frame_count = 0
                    fps_time = time.time()
                
                h, w = frame.shape[:2]
                cv2.putText(frame, f"FPS: {fps:.0f}", (w - 120, h - 15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 255, 100), 1)
                
                # Tashkent time overlay
                tashkent_time = now_tashkent().strftime("%H:%M:%S")
                cv2.putText(frame, f"UZB: {tashkent_time}", (w - 160, 55),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                
                # Display
                cv2.imshow(WINDOW_NAME, frame)
                
                # Keyboard
                self._handle_keyboard()
        
        except KeyboardInterrupt:
            print("\n[WARN] Interrupted by user")
        
        finally:
            self.stream.stop()
            cv2.destroyAllWindows()
            if self.engine:
                stats = self.engine.get_stats()
                print(f"\n📊 Final stats: {stats['total_count']} clients entered today")
            print("🏦 Client Counter stopped")


def main():
    """Entry point"""
    print("=" * 50)
    print("🏦 BANK CLIENT COUNTER")
    print("=" * 50)
    print(" Входящие клиенты — подсчёт через линию пересечения")
    print(" YOLO + ByteTrack | SQLite (local) + PostgreSQL (cloud)")
    print(f" Timezone: Tashkent (UTC+5) | Shift: {WORK_START} – {WORK_END}")
    print("=" * 50)
    
    counter = ClientCounter()
    counter.run()


if __name__ == "__main__":
    main()
