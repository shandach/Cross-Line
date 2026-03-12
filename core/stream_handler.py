"""
Video stream handler for RTSP camera
Чтение видеопотока с камеры входа
"""
import cv2
import os
import time
import threading
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CAMERA_URL, CAMERA_NAME, FRAME_WIDTH, FRAME_HEIGHT


class StreamHandler:
    """Handles video capture from RTSP stream asynchronously"""
    
    def __init__(self):
        self.url = CAMERA_URL
        self.name = CAMERA_NAME
        self.cap = None
        self.is_running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 50
        self.reconnect_delay = 5
        
        # Threading
        self.thread = None
        self.lock = threading.Lock()
        self.latest_frame = None
        self.last_read_success = False
        self.last_frame_time = 0.0
    
    def start(self) -> bool:
        """Start video capture thread"""
        if self.is_running:
            return True
        
        print(f"📹 [{self.name}] Starting stream handler...")
        self.is_running = True
        
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        
        # Wait for first frame
        timeout = 10.0
        start = time.time()
        while time.time() - start < timeout:
            with self.lock:
                if self.latest_frame is not None:
                    return True
            time.sleep(0.1)
        
        print(f"⚠️ [{self.name}] No frame received in {timeout}s")
        return self.is_running
    
    def _update(self):
        """Background thread loop"""
        self._connect()
        
        while self.is_running:
            if self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    with self.lock:
                        self.latest_frame = frame
                        self.last_read_success = True
                        self.last_frame_time = time.time()
                    self.reconnect_attempts = 0
                else:
                    with self.lock:
                        self.last_read_success = False
                    self._reconnect()
            else:
                self._reconnect()
            
            if not self.last_read_success:
                time.sleep(1.0)
    
    def _connect(self):
        """Connect to camera"""
        url = self.url
        try:
            if url.isdigit():
                self.cap = cv2.VideoCapture(int(url))
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
                self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            
            if self.cap.isOpened():
                width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"✅ [{self.name}] Connected: {width}x{height}")
            else:
                print(f"❌ [{self.name}] Failed to open stream")
        except Exception as e:
            print(f"❌ [{self.name}] Connection error: {e}")
    
    def _reconnect(self):
        """Reconnect logic"""
        self.reconnect_attempts += 1
        if self.reconnect_attempts > self.max_reconnect_attempts:
            print(f"💀 [{self.name}] Max reconnect attempts reached")
            self.is_running = False
            return
        
        print(f"🔄 [{self.name}] Reconnecting ({self.reconnect_attempts})...")
        if self.cap:
            self.cap.release()
        time.sleep(self.reconnect_delay)
        self._connect()
    
    def read_frame(self):
        """Read the latest frame"""
        if not self.is_running:
            return False, None
        
        with self.lock:
            if self.latest_frame is None:
                return False, None
            
            frame = self.latest_frame.copy()
            
            # Resize if needed
            if frame.shape[1] != FRAME_WIDTH or frame.shape[0] != FRAME_HEIGHT:
                frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
            
            return True, frame
    
    def get_frame_size(self):
        """Get current frame size"""
        if self.cap and self.cap.isOpened():
            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return (w, h)
        return (FRAME_WIDTH, FRAME_HEIGHT)
    
    def stop(self):
        """Stop video capture"""
        self.is_running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.cap:
            self.cap.release()
        print(f"📹 [{self.name}] Stream stopped")
