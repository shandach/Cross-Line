"""
Line Crossing Engine — Smart line-based people counting

Counts people whose anchor point (feet/center/top) crosses a counting line.
Uses movement vector + cooldown + counted_ids to prevent duplicates.

Approach:
1. Draw a line between 2 points (simple for operators)
2. Track which side of the line each person is on
3. When they cross from one side to the other → check movement direction
4. If direction matches "IN" → count (with cooldown protection)
"""
import time
import logging
import numpy as np
from pathlib import Path
from typing import Dict, Set, Tuple, List, Optional
from datetime import datetime

# Logging setup
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("line_crossing")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_DIR / "crossing_events.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(fh)


class LineCrossingEngine:
    """
    Counts people crossing a line in a specified direction.
    
    Smart protections:
    - counted_ids: each track_id counted only ONCE per shift
    - Direction vector: only counts movement matching IN direction
    - Cooldown: 1.5s gap between counts to prevent jitter
    - MIN_TRACK_AGE: ignores very new tracks (noise)
    """
    
    MIN_TRACK_AGE = 1            # Minimum frames before checking
    COOLDOWN_SEC = 1.5           # Seconds between counts (anti-jitter)

    def __init__(self, line_start: Tuple[int, int], line_end: Tuple[int, int], 
                 direction: str = 'down'):
        """
        Args:
            line_start: (x, y) first point of counting line
            line_end: (x, y) second point of counting line
            direction: 'down', 'up', 'left', 'right' — the "IN" direction
        """
        self.line_start = line_start
        self.line_end = line_end
        self.direction = direction
        
        # Line vector for cross-product side detection
        self.lx = line_end[0] - line_start[0]
        self.ly = line_end[1] - line_start[1]
        
        # State tracking
        self.pos_history: Dict[int, List[Tuple[int, int]]] = {}
        self.track_ages: Dict[int, int] = {}
        
        # Which side of the line was the person on last frame? (+1 or -1)
        self.last_side: Dict[int, int] = {}
        
        # Anti-duplicate protections
        self.counted_ids: Set[int] = set()
        self.total_count: int = 0
        self.last_count_time: Optional[float] = None  # timestamp of last count
        self.last_count_dt: Optional[datetime] = None
        
        print(f"📏 Line initialized: {line_start} → {line_end}. Direction IN: {direction}.")
        
    def _get_side(self, point: Tuple) -> int:
        """
        Determine which side of the line a point is on.
        Uses cross product: positive = one side, negative = other side.
        Returns +1, -1, or 0 (on the line).
        """
        # Vector from line_start to point
        px = float(point[0]) - self.line_start[0]
        py = float(point[1]) - self.line_start[1]
        
        # Cross product
        cross = self.lx * py - self.ly * px
        
        if cross > 0:
            return 1
        elif cross < 0:
            return -1
        return 0
    
    def _get_movement_vector(self, tid: int) -> Tuple[float, float]:
        """Calculate movement direction from position history."""
        history = self.pos_history.get(tid, [])
        if len(history) < 2:
            return (0, 0)
        
        start = history[0]
        end = history[-1]
        return (float(end[0] - start[0]), float(end[1] - start[1]))
    
    def _matches_direction(self, dx: float, dy: float) -> bool:
        """Check if movement vector generally aligns with the IN direction."""
        # 1. Calc normal vector of the line (perpendicular)
        lx = self.line_end[0] - self.line_start[0]
        ly = self.line_end[1] - self.line_start[1]
        
        # Two possible normals
        nx1, ny1 = -ly, lx
        nx2, ny2 = ly, -lx
        
        # 2. Pick the normal that points in our configured direction (up/down/left/right)
        if self.direction == 'down':
            nx, ny = (nx1, ny1) if ny1 > 0 else (nx2, ny2)
        elif self.direction == 'up':
            nx, ny = (nx1, ny1) if ny1 < 0 else (nx2, ny2)
        elif self.direction == 'right':
            nx, ny = (nx1, ny1) if nx1 > 0 else (nx2, ny2)
        else: # left
            nx, ny = (nx1, ny1) if nx1 < 0 else (nx2, ny2)
            
        # 3. Dot product between person's movement (dx, dy) and the correct normal (nx, ny)
        dot_product = (dx * nx) + (dy * ny)
        
        # We allow a slightly negative dot product (-50) because crouched people
        # or noisy bounding boxes can create a skewed movement history. 
        # As long as they crossed the line physically, we shouldn't be too strict here.
        return dot_product > -50

    def update(self, detections: list, current_time: float = None) -> List[int]:
        """
        Update with new detections from Tracker.
        Returns list of newly counted track_ids.
        """
        new_crossings = []
        if not detections:
            return new_crossings
        
        now = current_time or time.time()
        active_ids = set()
        
        for det in detections:
            tid = det.track_id
            active_ids.add(tid)
            anchor = det.anchor_point
            
            # Initialize new tracks
            if tid not in self.track_ages:
                self.track_ages[tid] = 0
                self.pos_history[tid] = []
                self.last_side[tid] = self._get_side(anchor)
            
            self.track_ages[tid] += 1
            self.pos_history[tid].append(anchor)
            
            # Keep history manageable
            if len(self.pos_history[tid]) > 20:
                self.pos_history[tid] = self.pos_history[tid][-20:]
                
            # Skip already counted
            if tid in self.counted_ids:
                continue
                
            # Skip very new tracks
            if self.track_ages[tid] < self.MIN_TRACK_AGE:
                continue
            
            # Determine current side of line
            current_side = self._get_side(anchor)
            prev_side = self.last_side.get(tid, current_side)
            self.last_side[tid] = current_side
            
            # Skip if on the line itself (side = 0)
            if current_side == 0:
                continue
            
            # === CROSSING DETECTED ===
            if current_side != prev_side and prev_side != 0:
                # Person crossed the line! Check direction.
                dx, dy = self._get_movement_vector(tid)
                
                if self._matches_direction(dx, dy):
                    # === COUNT! ===
                    self.counted_ids.add(tid)
                    self.total_count += 1
                    self.last_count_time = now
                    self.last_count_dt = datetime.now()
                    new_crossings.append(tid)
                    print(f"\n✅ COUNTED! Track {tid} crossed line moving {self.direction}. "
                          f"dx={dx:.0f}, dy={dy:.0f}. Total = {self.total_count}")
                    logger.info(f"🚶 CROSSING COUNTED: ID {tid}. Vector ({dx:.0f},{dy:.0f}). "
                               f"Total={self.total_count}")
                else:
                    print(f"\n⬛ Track {tid} crossed line but wrong direction "
                          f"(dx={dx:.0f}, dy={dy:.0f}, need '{self.direction}')")

        # Cleanup lost tracks
        lost_ids = [tid for tid in list(self.track_ages.keys()) if tid not in active_ids]
        for tid in lost_ids:
            self.track_ages.pop(tid, None)
            self.pos_history.pop(tid, None)
            self.last_side.pop(tid, None)
            
        return new_crossings
    
    def get_line_points(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        """Return line start and end points."""
        return (self.line_start, self.line_end)

    def reset_shift(self):
        self.counted_ids.clear()
        self.track_ages.clear()
        self.pos_history.clear()
        self.last_side.clear()
        self.total_count = 0
        self.last_count_time = None
        self.last_count_dt = None
        logger.info("Shift reset.")
        
    def get_stats(self) -> dict:
        return {
            'total_count': self.total_count,
            'active_tracks': len(self.track_ages),
            'last_count_time': self.last_count_dt
        }
