"""
YOLO + ByteTrack Person Tracker
Детектор и трекер людей для подсчёта пересечений
"""
import cv2
import numpy as np
import sys
from pathlib import Path
from typing import List, Tuple, NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    YOLO_MODEL, DETECTION_CONFIDENCE, PERSON_CLASS_ID, BASE_DIR,
    PERSON_MIN_ASPECT_RATIO, PERSON_MAX_WIDTH_RATIO,
    FRAME_WIDTH
)


class TrackingDetection(NamedTuple):
    """Detection with tracking ID"""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    center: Tuple[int, int]          # center x, y
    track_id: int                    # ByteTrack persistent ID
    anchor_point: Tuple[int, int]    # Configurable tracking point (bottom, center, top)


class TrackingDetector:
    """
    YOLO + ByteTrack for persistent person tracking.
    Each detected person gets a unique track_id.
    """
    
    def __init__(self, model_path: str = None):
        """Initialize tracking detector"""
        from ultralytics import YOLO
        
        if model_path is None:
            model_path = str(BASE_DIR / YOLO_MODEL)
            # Fallback: try parent project's model
            if not Path(model_path).exists():
                fallback = BASE_DIR.parent.parent / "Cam" / "workplace-monitoring" / YOLO_MODEL
                if fallback.exists():
                    model_path = str(fallback)

        # === MODEL LOADING ===
        try:
            print(f"Loading PyTorch model: {model_path}")
            self.model = YOLO(model_path, task='detect')
        except Exception as e:
            print(f"⚠️ Error loading model: {e}")
            print("Fallback to standard YOLO load")
            self.model = YOLO(YOLO_MODEL, task='detect')
        # === MODEL LOADING END ===
        
        self.confidence = DETECTION_CONFIDENCE
        
        # ByteTrack config — use custom if available, else default
        self.tracker_config = "bytetrack.yaml"
        custom_tracker = BASE_DIR / "bytetrack_custom.yaml"
        if custom_tracker.exists():
            self.tracker_config = str(custom_tracker)
        
        print("✅ Tracking detector loaded")
    
    def detect(self, frame: np.ndarray) -> List[TrackingDetection]:
        """
        Detect and track persons in frame.
        
        Returns:
            List of TrackingDetection with track_id and foot_center
        """
        results = self.model.track(
            frame,
            classes=[PERSON_CLASS_ID],
            conf=self.confidence,
            tracker=self.tracker_config,
            persist=True,
            verbose=False
        )
        
        detections = []
        
        for result in results:
            boxes = result.boxes
            if boxes is None or boxes.id is None:
                continue
            
            for i, box in enumerate(boxes):
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                confidence = float(box.conf[0].cpu().numpy())
                track_id = int(box.id[0].cpu().numpy())
                
                # Check dimensions
                w = x2 - x1
                h = y2 - y1
                
                # 1. Aspect Ratio Filter (Humans are taller than wide)
                if h < w * PERSON_MIN_ASPECT_RATIO:
                    continue  # Skip wide objects (bags, chairs, shadows)
                
                # 2. Size Filter (Too big = camera artifact / occlusion)
                if w > FRAME_WIDTH * PERSON_MAX_WIDTH_RATIO:
                    continue
                
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
                
                # Dynamic anchor point based on config
                from config import TRACKING_ANCHOR
                if TRACKING_ANCHOR == 'center':
                    anchor_x, anchor_y = center_x, center_y
                elif TRACKING_ANCHOR == 'top':
                    anchor_x, anchor_y = center_x, y1
                else:  # default 'bottom'
                    anchor_x, anchor_y = center_x, y2
                
                detection = TrackingDetection(
                    bbox=(x1, y1, x2, y2),
                    confidence=confidence,
                    center=(center_x, center_y),
                    track_id=track_id,
                    anchor_point=(anchor_x, anchor_y)
                )
                detections.append(detection)
        
        return detections
    
    def reset_tracker(self):
        """Reset tracker — call at shift end to reset IDs"""
        self.model.predictor = None
        print("🔄 Tracker reset — IDs start from 1")
    
    def draw_detections(self, frame: np.ndarray, detections: List[TrackingDetection],
                        counted_ids: set = None) -> np.ndarray:
        """Draw detection boxes with track IDs"""
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            
            is_counted = counted_ids and det.track_id in counted_ids
            color = (0, 255, 0) if is_counted else (255, 0, 255)
            
            # Bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Track ID label
            label = f"ID:{det.track_id}"
            if is_counted:
                label += " ✓"
            
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(frame, label, (x1 + 2, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Anchor point dot (used for zone tracking)
            cv2.circle(frame, det.anchor_point, 4, (0, 255, 255), -1)
        
        return frame
