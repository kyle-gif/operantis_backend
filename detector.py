import mss
from ultralytics import YOLO
from threading import Lock
import cv2
import numpy as np

# ==============================================================================
# ★★★ Final Verified Zone Definitions (Tower Positions Re-calibrated) ★★★
# 사용자의 피드백을 반영하여 탑/봇 2,3차 및 미드 1,2,3차 타워 위치를 정밀 재조정한 버전입니다.
# ==============================================================================
ZONE_DEFINITIONS = [
    # --- Major Objectives (Neutral) ---
    {"name": "Baron Pit", "coords": (0.355, 0.245), "radius": 0.06},
    {"name": "Dragon Pit",   "coords": (0.645, 0.755), "radius": 0.06},

    # --- Jungle Camps ---
    {"name": "Blue Team Blue Buff", "coords": (0.185, 0.65), "radius": 0.045},
    {"name": "Blue Team Red Buff", "coords": (0.37, 0.81), "radius": 0.045},
    {"name": "Red Team Blue Buff", "coords": (0.815, 0.35), "radius": 0.045},
    {"name": "Red Team Red Buff", "coords": (0.63, 0.19), "radius": 0.045},

    # --- Blue Team Structures (Order / Bottom-Left) ---
    # Top Lane
    {"name": "Blue Top T1 Tower", "coords": (0.09, 0.28), "radius": 0.035},
    {"name": "Blue Top T2 Tower", "coords": (0.19, 0.47), "radius": 0.04},      # 수정됨
    {"name": "Blue Top T3 Tower", "coords": (0.16, 0.64), "radius": 0.04},      # 수정됨
    {"name": "Blue Top Inhibitor", "coords": (0.1, 0.71), "radius": 0.03},
    # Mid Lane
    {"name": "Blue Mid T1 Tower", "coords": (0.40, 0.60), "radius": 0.04},      # 수정됨
    {"name": "Blue Mid T2 Tower", "coords": (0.32, 0.68), "radius": 0.04},      # 수정됨
    {"name": "Blue Mid T3 Tower", "coords": (0.24, 0.76), "radius": 0.04},      # 수정됨
    {"name": "Blue Mid Inhibitor", "coords": (0.17, 0.81), "radius": 0.03},
    # Bot Lane
    {"name": "Blue Bot T1 Tower", "coords": (0.72, 0.91), "radius": 0.035},
    {"name": "Blue Bot T2 Tower", "coords": (0.53, 0.81), "radius": 0.04},      # 수정됨
    {"name": "Blue Bot T3 Tower", "coords": (0.35, 0.86), "radius": 0.04},      # 수정됨
    {"name": "Blue Bot Inhibitor", "coords": (0.28, 0.9), "radius": 0.03},
    # Nexus
    {"name": "Blue Nexus Turret (Top)", "coords": (0.1, 0.85), "radius": 0.03},
    {"name": "Blue Nexus Turret (Bottom)", "coords": (0.15, 0.9), "radius": 0.03},
    {"name": "Blue Nexus", "coords": (0.07, 0.93), "radius": 0.04},

    # --- Red Team Structures (Chaos / Top-Right) ---
    # Top Lane
    {"name": "Red Top T1 Tower", "coords": (0.28, 0.09), "radius": 0.035},
    {"name": "Red Top T2 Tower", "coords": (0.47, 0.19), "radius": 0.04},      # 수정됨
    {"name": "Red Top T3 Tower", "coords": (0.64, 0.16), "radius": 0.04},      # 수정됨
    {"name": "Red Top Inhibitor", "coords": (0.72, 0.1), "radius": 0.03},
    # Mid Lane
    {"name": "Red Mid T1 Tower", "coords": (0.60, 0.40), "radius": 0.04},      # 수정됨
    {"name": "Red Mid T2 Tower", "coords": (0.68, 0.32), "radius": 0.04},      # 수정됨
    {"name": "Red Mid T3 Tower", "coords": (0.76, 0.24), "radius": 0.04},      # 수정됨
    {"name": "Red Mid Inhibitor", "coords": (0.83, 0.19), "radius": 0.03},
    # Bot Lane
    {"name": "Red Bot T1 Tower", "coords": (0.91, 0.72), "radius": 0.035},
    {"name": "Red Bot T2 Tower", "coords": (0.81, 0.53), "radius": 0.04},      # 수정됨
    {"name": "Red Bot T3 Tower", "coords": (0.86, 0.35), "radius": 0.04},      # 수정됨
    {"name": "Red Bot Inhibitor", "coords": (0.9, 0.28), "radius": 0.03},
    # Nexus
    {"name": "Red Nexus Turret (Top)", "coords": (0.85, 0.1), "radius": 0.03},
    {"name": "Red Nexus Turret (Bottom)", "coords": (0.9, 0.15), "radius": 0.03},
    {"name": "Red Nexus", "coords": (0.93, 0.07), "radius": 0.04},
]
MINIMAP_SCALE = 0.25

class MinimapDetector:
    def __init__(self, model_path, show_preview=True):
        self.model = YOLO(model_path)
        self.show_preview = show_preview
        self.running = False
        self.detected_objects = []
        self.lock = Lock()
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            roi_height = int(monitor["height"] * MINIMAP_SCALE)
            roi_width = roi_height
            roi_left = monitor["width"] - roi_width
            roi_top = monitor["height"] - roi_height
            self.minimap_roi = {"top": roi_top, "left": roi_left, "width": roi_width, "height": roi_height}
        print(f"탐지할 미니맵 영역이 자동으로 설정되었습니다: {self.minimap_roi}")

    def start_detection_thread(self, conf_threshold=0.5):
        self.running = True
        print("미니맵 탐지 스레드를 시작합니다.")
        with mss.mss() as sct:
            while self.running:
                sct_img = sct.grab(self.minimap_roi)
                frame = np.array(sct_img)
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                results = self.model(frame_bgr, conf=conf_threshold, verbose=False)
                current_detections = []
                for r in results:
                    for box in r.boxes:
                        class_id = int(box.cls[0])
                        class_name = self.model.names[class_id]
                        x_norm, y_norm, _, _ = box.xywhn[0].tolist()
                        current_detections.append({"tag": class_name, "x_norm": x_norm, "y_norm": y_norm})
                with self.lock:
                    self.detected_objects = current_detections
                if self.show_preview:
                    annotated_frame = results[0].plot()
                    h, w, _ = annotated_frame.shape
                    for zone in ZONE_DEFINITIONS:
                        center_x_px = int(zone["coords"][0] * w)
                        center_y_px = int(zone["coords"][1] * h)
                        radius_px = int(zone["radius"] * w)
                        overlay = annotated_frame.copy()
                        cv2.circle(overlay, (center_x_px, center_y_px), radius_px, (0, 255, 255), -1)
                        alpha = 0.3
                        annotated_frame = cv2.addWeighted(overlay, alpha, annotated_frame, 1 - alpha, 0)
                        cv2.circle(annotated_frame, (center_x_px, center_y_px), radius_px, (0, 200, 200), 1)
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        font_scale = 0.3
                        font_thickness = 1
                        text_color = (255, 255, 255)
                        cv2.putText(annotated_frame, zone["name"], (center_x_px - radius_px, center_y_px), font,
                                    font_scale, text_color, font_thickness)
                    #cv2.imshow('LoL Minimap Detection', annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.running = False
        self.stop()
        print("미니맵 탐지가 종료되었습니다.")

    def get_detected_objects(self):
        with self.lock:
            return list(self.detected_objects)

    def stop(self):
        self.running = False
        if self.show_preview:
            cv2.destroyAllWindows()