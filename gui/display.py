"""
Display module — Отрисовка линии, статистики и режима настройки
"""
import cv2
import numpy as np
from datetime import datetime, date
from typing import List, Optional, Tuple


def draw_counting_line(frame: np.ndarray, line_start: Tuple[int, int], 
                       line_end: Tuple[int, int], color=(0, 0, 255), 
                       thickness=3) -> np.ndarray:
    """Отрисовка линии подсчёта"""
    cv2.line(frame, line_start, line_end, color, thickness, cv2.LINE_AA)
    
    # Small circles at endpoints
    cv2.circle(frame, line_start, 6, color, -1)
    cv2.circle(frame, line_end, 6, color, -1)
    
    return frame


def draw_direction_arrow(frame: np.ndarray, line_start: Tuple[int, int], 
                         line_end: Tuple[int, int], direction: str, 
                         color=(0, 255, 0)) -> np.ndarray:
    """Нарисовать стрелку направления входа в центре линии"""
    cx = (line_start[0] + line_end[0]) // 2
    cy = (line_start[1] + line_end[1]) // 2
        
    arrow_len = 50
    start = (cx, cy)
    end = start
    
    if direction == 'down':
        end = (cx, cy + arrow_len)
    elif direction == 'up':
        end = (cx, cy - arrow_len)
    elif direction == 'right':
        end = (cx + arrow_len, cy)
    elif direction == 'left':
        end = (cx - arrow_len, cy)
        
    # Draw arrow
    frame = cv2.arrowedLine(frame, start, end, color, 3, tipLength=0.3)
    
    # Direction text
    cv2.putText(frame, f"IN: {direction.upper()}", (cx + 10, cy - 10),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    return frame


def draw_stats_table(frame: np.ndarray, total_count: int, 
                     hourly_data: List[dict], last_entry_time: Optional[datetime],
                     work_start: str = "08:45", work_end: str = "18:15",
                     position: str = "right") -> np.ndarray:
    """Нарисовать таблицу статистики на кадре."""
    h, w = frame.shape[:2]
    
    table_w = 280
    padding = 10
    row_h = 28
    header_h = 45
    
    num_hours = len(hourly_data)
    total_rows = 4 + num_hours
    table_h = header_h + total_rows * row_h + padding * 2
    
    if position == "right":
        x0 = w - table_w - 15
    else:
        x0 = 15
    y0 = 15
    
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + table_w, y0 + table_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)
    
    cv2.rectangle(frame, (x0, y0), (x0 + table_w, y0 + table_h), (100, 100, 100), 1)
    
    cv2.rectangle(frame, (x0, y0), (x0 + table_w, y0 + header_h), (0, 100, 200), -1)
    cv2.putText(frame, "STATISTIKA", (x0 + 65, y0 + 20),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, f"Smena: {work_start} - {work_end}", (x0 + 45, y0 + 40),
               cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 255), 1)
    
    y = y0 + header_h + padding
    
    cv2.putText(frame, f"JAMI KIRGANLAR:", (x0 + padding, y + 18),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
    y += row_h
    
    count_text = str(total_count)
    (tw, th), _ = cv2.getTextSize(count_text, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)
    cv2.putText(frame, count_text, (x0 + (table_w - tw) // 2, y + 30),
               cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
    y += row_h + 20
    
    cv2.line(frame, (x0 + padding, y), (x0 + table_w - padding, y), (80, 80, 80), 1)
    y += 8
    
    cv2.putText(frame, "Soatlik:", (x0 + padding, y + 15),
               cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)
    y += row_h
    
    start_hour = int(work_start.split(":")[0])
    end_hour = int(work_end.split(":")[0])
    
    hourly_dict = {h['hour']: h['count'] for h in hourly_data}
    
    for hour in range(start_hour, end_hour + 1):
        count = hourly_dict.get(hour, 0)
        time_str = f"{hour:02d}:00 - {hour+1:02d}:00"
        
        current_hour = datetime.now().hour
        if hour == current_hour:
            cv2.rectangle(frame, (x0 + 5, y), (x0 + table_w - 5, y + row_h - 2), 
                         (40, 60, 40), -1)
            text_color = (0, 255, 100)
        else:
            text_color = (200, 200, 200) if count > 0 else (100, 100, 100)
        
        cv2.putText(frame, time_str, (x0 + padding, y + 18),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, text_color, 1)
        cv2.putText(frame, str(count), (x0 + table_w - 50, y + 18),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, text_color, 1 if count == 0 else 2)
        y += row_h
    
    cv2.line(frame, (x0 + padding, y), (x0 + table_w - padding, y), (80, 80, 80), 1)
    y += 8
    
    if last_entry_time:
        last_str = last_entry_time.strftime("%H:%M:%S")
    else:
        last_str = "---"
    cv2.putText(frame, f"Oxirgi kirish: {last_str}", (x0 + padding, y + 18),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    
    return frame


def draw_big_counter(frame: np.ndarray, count: int, 
                     position: Tuple[int, int] = None) -> np.ndarray:
    """Нарисовать большой счётчик в углу"""
    h, w = frame.shape[:2]
    
    if position is None:
        position = (15, 80)
    
    x, y = position
    
    text = f"Kirganlar: {count}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
    cv2.rectangle(frame, (x - 5, y - th - 10), (x + tw + 10, y + 10), (0, 0, 0), -1)
    cv2.rectangle(frame, (x - 5, y - th - 10), (x + tw + 10, y + 10), (0, 200, 0), 2)
    
    cv2.putText(frame, text, (x, y),
               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
    
    return frame


def draw_shift_status(frame: np.ndarray, work_start: str, work_end: str,
                      is_active: bool) -> np.ndarray:
    """Показать статус рабочей смены"""
    h, w = frame.shape[:2]
    
    now_str = datetime.now().strftime("%H:%M:%S")
    
    if is_active:
        status = f"SMENA FAOL | {now_str}"
        color = (0, 255, 0)
    else:
        status = f"SMENA TUGADI | {now_str}"
        color = (0, 0, 255)
    
    (tw, th), _ = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x = w - tw - 15
    y = h - 15
    
    cv2.rectangle(frame, (x - 5, y - th - 5), (x + tw + 5, y + 5), (0, 0, 0), -1)
    cv2.putText(frame, status, (x, y),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    
    return frame


def draw_line_setup_mode(frame: np.ndarray, points: list, 
                         mouse_pos: Tuple[int, int] = None) -> np.ndarray:
    """Режим рисования линии (интерактивный, 2 точки)"""
    overlay = frame.copy()
    
    cv2.rectangle(overlay, (0, 0), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
    frame = cv2.addWeighted(overlay, 0.3, frame, 0.7, 0)
    
    cv2.putText(frame, "=== LINE SETUP MODE ===", (50, 50),
               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    cv2.putText(frame, "Click 2 points to draw a counting line across the entrance.", (50, 85),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
               
    pts_drawn = len(points)
    
    if pts_drawn > 0:
        # First point
        cv2.circle(frame, points[0], 8, (0, 0, 255), -1)
        cv2.circle(frame, points[0], 12, (0, 0, 255), 2)
        
        if pts_drawn == 2:
            # Both points — draw the line
            cv2.line(frame, points[0], points[1], (0, 255, 0), 3, cv2.LINE_AA)
            cv2.circle(frame, points[1], 8, (0, 0, 255), -1)
            cv2.circle(frame, points[1], 12, (0, 0, 255), 2)
        elif mouse_pos:
            # Preview line to mouse
            cv2.line(frame, points[0], mouse_pos, (0, 255, 255), 2, cv2.LINE_AA)
            
    if pts_drawn == 2:
        cv2.putText(frame, "Press 'Q' or 'Enter' to SAVE line", (50, 120),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    elif pts_drawn == 1:
        cv2.putText(frame, "Click second point...", (50, 120),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
    else:
        cv2.putText(frame, "Click first point...", (50, 120),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
                   
    return frame


def format_duration(seconds: float) -> str:
    """Форматировать длительность"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
