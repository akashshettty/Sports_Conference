from __future__ import annotations

import time
import threading
import json
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

try:
    import mediapipe as mp
except Exception as e:
    mp = None

import requests


# -----------------------------
# Configuration
# -----------------------------

API_BASE = "http://127.0.0.1:5000/api"  # Update if server runs elsewhere

# Stabilization parameters
STABLE_MIN_DURATION_SEC = 0.6  # require gesture to be stable for this many seconds
MIN_CONFIDENCE = 0.85          # minimum confidence to accept a gesture
COOLDOWN_SEC = 1.2             # cooldown after accepting a gesture to avoid repeats

# Visualization toggle
SHOW_OVERLAY = True


# -----------------------------
# Gesture command definitions
# -----------------------------

class GestureType:
    NONE = "none"
    ONE_FINGER = "one_finger"      # +1 Team A
    TWO_FINGERS = "two_fingers"    # +1 Team B
    FIST = "fist"                  # Undo
    SWIPE_RIGHT = "swipe_right"    # Next set
    SWIPE_LEFT = "swipe_left"      # Reset match


@dataclass
class GestureDetection:
    kind: str
    confidence: float
    timestamp: float
    meta: Optional[dict] = None


class GestureStabilizer:
    """Tracks the most recent gesture and accepts it if stable long enough with confidence."""

    def __init__(self, min_duration_sec: float, min_confidence: float, cooldown_sec: float):
        self.min_duration_sec = min_duration_sec
        self.min_confidence = min_confidence
        self.cooldown_sec = cooldown_sec
        self._current: Optional[GestureDetection] = None
        self._accepted_at: float = 0.0

    def update(self, detection: GestureDetection) -> Optional[GestureDetection]:
        now = time.time()
        # Cooldown: do not accept new gestures during cooldown
        if (now - self._accepted_at) < self.cooldown_sec:
            return None
        # If type changes, reset
        if not self._current or self._current.kind != detection.kind:
            self._current = detection
            return None
        # Same type: keep the higher confidence and earliest start
        if detection.confidence > self._current.confidence:
            self._current.confidence = detection.confidence
        # Check stability
        if (now - self._current.timestamp) >= self.min_duration_sec and self._current.confidence >= self.min_confidence:
            self._accepted_at = now
            accepted = self._current
            self._current = None
            return accepted
        return None


class GestureRecognizer:
    """MediaPipe-based hand landmark detector with simple rule-based gesture recognition.

    - 1 finger up: index extended → ONE_FINGER
    - 2 fingers up: index + middle extended → TWO_FINGERS
    - Fist: all fingers folded → FIST
    - Swipe: track wrist x displacement velocity → SWIPE_LEFT/RIGHT
    """

    def __init__(self):
        self.mode = "mediapipe" if mp is not None else "opencv"
        self._last_wrist: Optional[Tuple[float, float, float]] = None  # (x, y, t)
        if self.mode == "mediapipe":
            self.mp_hands = mp.solutions.hands
            self.hands = self.mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                model_complexity=0,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.mp_drawing = mp.solutions.drawing_utils
        else:
            # OpenCV-only fallback needs no init beyond keeping centroid history
            self._last_centroid: Optional[Tuple[float, float, float]] = None

    def close(self):
        if self.mode == "mediapipe":
            try:
                self.hands.close()
            except Exception:
                pass

    @staticmethod
    def _count_extended_fingers(landmarks) -> int:
        # landmarks: list of 21 NormalizedLandmark
        # Finger tip indices per MediaPipe: thumb 4, index 8, middle 12, ring 16, pinky 20
        # Approach: compare tip y with pip y (lower y means higher in image). For simplicity, ignore thumb.
        tip_ids = [8, 12, 16, 20]
        pip_ids = [6, 10, 14, 18]
        extended = 0
        for tip, pip in zip(tip_ids, pip_ids):
            if landmarks[tip].y < landmarks[pip].y:
                extended += 1
        return extended

    def recognize(self, frame_bgr) -> Tuple[GestureDetection, Optional[object]]:
        h, w = frame_bgr.shape[:2]
        if self.mode == "mediapipe":
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            result = self.hands.process(frame_rgb)
            overlay = None

            if result.multi_hand_landmarks:
                hand_landmarks = result.multi_hand_landmarks[0]
                # Count fingers
                count = self._count_extended_fingers(hand_landmarks.landmark)
                # Heuristic confidence from detection score; refine with count mapping confidence
                det_conf = result.multi_handedness[0].classification[0].score if result.multi_handedness else 0.5
                conf = float(det_conf)

                kind = GestureType.NONE
                if count == 0:
                    kind = GestureType.FIST
                    conf = max(conf, 0.9)
                elif count == 1:
                    kind = GestureType.ONE_FINGER
                    conf = max(conf, 0.9)
                elif count == 2:
                    kind = GestureType.TWO_FINGERS
                    conf = max(conf, 0.9)

                # Swipe detection using wrist velocity
                wrist = hand_landmarks.landmark[0]  # wrist
                t = time.time()
                if self._last_wrist is not None:
                    last_x, _, last_t = self._last_wrist
                    dx = (wrist.x - last_x)
                    dt = max(1e-3, (t - last_t))
                    vx = dx / dt
                    if abs(vx) > 1.8:
                        kind = GestureType.SWIPE_RIGHT if vx > 0 else GestureType.SWIPE_LEFT
                        conf = 0.95
                self._last_wrist = (wrist.x, wrist.y, t)

                if SHOW_OVERLAY:
                    overlay = (hand_landmarks, self.mp_hands, self.mp_drawing)

                return GestureDetection(kind=kind, confidence=conf, timestamp=time.time()), overlay

            # No hands detected
            self._last_wrist = None
            return GestureDetection(kind=GestureType.NONE, confidence=0.0, timestamp=time.time()), None

        # OpenCV-only fallback path
        overlay_img = None
        # Basic skin segmentation in HSV
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 30, 60])
        upper = np.array([20, 150, 255])
        mask1 = cv2.inRange(hsv, lower, upper)
        lower2 = np.array([160, 30, 60])
        upper2 = np.array([179, 150, 255])
        mask2 = cv2.inRange(hsv, lower2, upper2)
        mask = cv2.bitwise_or(mask1, mask2)
        mask = cv2.GaussianBlur(mask, (7,7), 0)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            self._last_centroid = None
            return GestureDetection(kind=GestureType.NONE, confidence=0.0, timestamp=time.time()), None

        cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        if area < 1500:
            self._last_centroid = None
            return GestureDetection(kind=GestureType.NONE, confidence=0.0, timestamp=time.time()), None

        hull = cv2.convexHull(cnt, returnPoints=False)
        defects = None
        if hull is not None and len(hull) > 3:
            defects = cv2.convexityDefects(cnt, hull)

        fingers = 0
        if defects is not None:
            for i in range(defects.shape[0]):
                s, e, f, d = defects[i, 0]
                start = cnt[s][0]
                end = cnt[e][0]
                far = cnt[f][0]
                a = np.linalg.norm(end - start)
                b = np.linalg.norm(far - start)
                c = np.linalg.norm(end - far)
                # Angle at the defect; small angle suggests finger separation
                if b > 1e-5 and c > 1e-5:
                    angle = np.degrees(np.arccos((b*b + c*c - a*a) / (2*b*c)))
                    if angle < 80 and d > 1000:
                        fingers += 1
        # Heuristic: num_fingers ≈ defects + 1 (cap at 5)
        fingers = min(5, fingers + 1) if defects is not None else 0

        kind = GestureType.NONE
        conf = 0.6
        if fingers == 0:
            kind = GestureType.FIST
            conf = 0.9
        elif fingers == 1:
            kind = GestureType.ONE_FINGER
            conf = 0.85
        elif fingers == 2:
            kind = GestureType.TWO_FINGERS
            conf = 0.85

        # Swipe detection via centroid velocity
        M = cv2.moments(cnt)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"]) / float(w)
            cy = int(M["m01"] / M["m00"]) / float(h)
            t = time.time()
            if self._last_centroid is not None:
                lx, ly, lt = self._last_centroid
                dx = cx - lx
                dt = max(1e-3, (t - lt))
                vx = dx / dt
                if abs(vx) > 1.2:
                    kind = GestureType.SWIPE_RIGHT if vx > 0 else GestureType.SWIPE_LEFT
                    conf = 0.95
            self._last_centroid = (cx, cy, t)

        if SHOW_OVERLAY:
            overlay_img = frame_bgr.copy()
            cv2.drawContours(overlay_img, [cnt], -1, (0,255,0), 2)
            cv2.putText(overlay_img, f"fingers={fingers}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 1, cv2.LINE_AA)

        return GestureDetection(kind=kind, confidence=conf, timestamp=time.time()), overlay_img


def _post_api(path: str, payload: dict) -> bool:
    try:
        url = f"{API_BASE}{path}"
        r = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload), timeout=2.5)
        return r.status_code >= 200 and r.status_code < 300
    except Exception:
        return False


def send_command(match_id: int, gesture: GestureDetection) -> bool:
    """Map gesture to backend command and send to the Flask API endpoints.
    Returns True if a command was sent successfully.
    """
    if gesture.kind == GestureType.ONE_FINGER:
        return _post_api(f"/matches/{match_id}/gesture_command", {"command": "point_a"})
    if gesture.kind == GestureType.TWO_FINGERS:
        return _post_api(f"/matches/{match_id}/gesture_command", {"command": "point_b"})
    if gesture.kind == GestureType.FIST:
        return _post_api(f"/matches/{match_id}/gesture_command", {"command": "undo"})
    if gesture.kind == GestureType.SWIPE_RIGHT:
        return _post_api(f"/matches/{match_id}/gesture_command", {"command": "next_set"})
    if gesture.kind == GestureType.SWIPE_LEFT:
        return _post_api(f"/matches/{match_id}/gesture_command", {"command": "reset_match"})
    return False


def run_gesture_loop(match_id: int, camera_index: int = 0, resize_width: int = 640) -> None:
    """Main loop to capture webcam frames, recognize gestures, and send commands.

    - match_id: integer match id from your backend
    - camera_index: default 0; choose your webcam
    - resize_width: frame is resized to this width to improve latency
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError("Could not open webcam. Check camera_index or permissions.")

    recognizer = GestureRecognizer()
    stabilizer = GestureStabilizer(STABLE_MIN_DURATION_SEC, MIN_CONFIDENCE, COOLDOWN_SEC)

    try:
        last_sent: Optional[str] = None
        last_send_ts: float = 0.0
        font = cv2.FONT_HERSHEY_SIMPLEX
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            # Resize for latency
            if resize_width and frame.shape[1] != resize_width:
                scale = resize_width / frame.shape[1]
                frame = cv2.resize(frame, (resize_width, int(frame.shape[0] * scale)))

            detection, overlay = recognizer.recognize(frame)
            accepted = stabilizer.update(detection)

            # Draw overlay
            if SHOW_OVERLAY:
                if overlay is not None:
                    # MediaPipe path provides (hand_landmarks, mp_hands, mp_drawing)
                    if isinstance(overlay, tuple) and len(overlay) == 3:
                        hand_landmarks, mp_hands, mp_drawing = overlay
                        mp_drawing.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                    # OpenCV fallback returns an image overlay
                    elif isinstance(overlay, np.ndarray):
                        frame = overlay
                # HUD
                cv2.putText(frame, f"gesture={detection.kind} conf={detection.confidence:.2f}", (10, 24), font, 0.6, (0,255,0), 1, cv2.LINE_AA)
                if accepted:
                    cv2.putText(frame, f"ACCEPTED: {accepted.kind}", (10, 48), font, 0.7, (0,0,255), 2, cv2.LINE_AA)

            # Send if accepted
            if accepted:
                if send_command(match_id, accepted):
                    last_sent = accepted.kind
                    last_send_ts = time.time()

            if SHOW_OVERLAY:
                cv2.imshow("Gesture Control", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == 27 or key == ord('q'):
                    break
    finally:
        try:
            recognizer.close()
        except Exception:
            pass
        try:
            cap.release()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Gesture-based scoring for badminton scoreboard")
    p.add_argument("--match-id", type=int, required=True, help="Active match id")
    p.add_argument("--camera", type=int, default=0, help="Webcam camera index")
    p.add_argument("--width", type=int, default=640, help="Resize width for frames")
    p.add_argument("--no-overlay", action="store_true", help="Disable overlay window")
    p.add_argument("--api", type=str, default=API_BASE, help="API base URL, e.g. http://localhost:5000/api")
    args = p.parse_args()
    if args.no_overlay:
        SHOW_OVERLAY = False
    API_BASE = args.api.rstrip('/')
    run_gesture_loop(match_id=args.match_id, camera_index=args.camera, resize_width=args.width)


