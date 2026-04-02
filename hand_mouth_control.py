import ctypes

# Fix: mediapipe shared lib does not export 'free' on Windows (Python 3.13)
_orig_cdll_getitem = ctypes.CDLL.__getitem__

def _patched_cdll_getitem(self, name_or_ordinal):
    try:
        return _orig_cdll_getitem(self, name_or_ordinal)
    except AttributeError:
        if name_or_ordinal == "free":
            return _orig_cdll_getitem(ctypes.CDLL("ucrtbase.dll"), "free")
        raise

ctypes.CDLL.__getitem__ = _patched_cdll_getitem

import math
import time
import cv2
import numpy as np
try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.core.base_options import BaseOptions
import mediapipe as mp
import os

# ═══════════════════════════════════════════════════════════════
# مسارات النماذج (نسبية للمجلد الحالي)
# ═══════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HAND_MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")
FACE_MODEL_PATH = os.path.join(SCRIPT_DIR, "face_landmarker.task")

# ═══════════════════════════════════════════════════════════════
# إعدادات التحكم
# ═══════════════════════════════════════════════════════════════

# وضع التحكم: "HAND" = اليد، "MOUTH" = الفم، "BOTH" = كلاهما
CONTROL_MODE = "BOTH"

# ─── إعدادات اليد ───
MIN_DIST = 10.0
MAX_DIST = 200.0

# ─── إعدادات الفم ───
MIN_MOUTH_RATIO = 0.02
MAX_MOUTH_RATIO = 0.15

# ─── نطاق الخرج ───
MIN_VALUE = 0
MAX_VALUE = 180

# ─── إعدادات Arduino ───
ARDUINO_PORT = "COM23"
ARDUINO_BAUD = 9600
ARDUINO_PIN = 9
ARDUINO_BOOT_WAIT_SEC = 2.5
ARDUINO_RECONNECT_SEC = 5.0
SERIAL_ENABLED = True

# ─── إعدادات الكاميرا والأداء ───
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
SERIAL_SEND_INTERVAL_SEC = 0.03
SERIAL_MIN_DELTA = 2

# ─── نقاط الفم ───
UPPER_LIP_IDX = 13
LOWER_LIP_IDX = 14
FOREHEAD_IDX = 10
CHIN_IDX = 152
MOUTH_OUTLINE = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
                 78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]

# ─── نقاط اليد ───
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def hand_dist_to_value(distance: float) -> int:
    distance = clamp(distance, MIN_DIST, MAX_DIST)
    normalized = (distance - MIN_DIST) / (MAX_DIST - MIN_DIST)
    return int(normalized * (MAX_VALUE - MIN_VALUE) + MIN_VALUE)


def mouth_ratio_to_value(ratio: float) -> int:
    ratio = clamp(ratio, MIN_MOUTH_RATIO, MAX_MOUTH_RATIO)
    normalized = (ratio - MIN_MOUTH_RATIO) / (MAX_MOUTH_RATIO - MIN_MOUTH_RATIO)
    return int(normalized * (MAX_VALUE - MIN_VALUE) + MIN_VALUE)


def send_value(arduino_obj, value: int) -> bool:
    try:
        arduino_obj.write(f"{value}\n".encode("ascii"))
        return True
    except Exception as exc:
        print(f"Serial write failed: {exc}")
        return False


def detect_arduino_port(preferred_port: str | None = None) -> str | None:
    if serial is None or list_ports is None:
        return preferred_port
    ports = list(list_ports.comports())
    if preferred_port:
        for p in ports:
            if p.device.upper() == preferred_port.upper():
                return p.device
    for p in ports:
        desc = f"{p.description} {p.manufacturer or ''}".lower()
        if "arduino" in desc or "ch340" in desc or "usb serial" in desc:
            return p.device
    return ports[0].device if ports else None


def list_available_ports() -> list[str]:
    if list_ports is None:
        return []
    return [p.device for p in list_ports.comports()]


def connect_arduino(preferred_port: str | None):
    if serial is None:
        return None
    available_ports = list_available_ports()
    if available_ports:
        print(f"Available COM ports: {', '.join(available_ports)}")
    else:
        print("No COM ports detected.")

    candidate_ports: list[str] = []
    if preferred_port:
        candidate_ports.append(preferred_port)
    auto_port = detect_arduino_port(preferred_port)
    if auto_port and auto_port not in candidate_ports:
        candidate_ports.append(auto_port)
    for port in available_ports:
        if port not in candidate_ports:
            candidate_ports.append(port)

    if not candidate_ports:
        return None

    for port in candidate_ports:
        try:
            arduino_obj = serial.Serial(port, ARDUINO_BAUD, timeout=1.0)
            time.sleep(ARDUINO_BOOT_WAIT_SEC)
            arduino_obj.reset_input_buffer()
            arduino_obj.reset_output_buffer()
            arduino_obj.flush()
            print(f"Arduino connected on {port} @ {ARDUINO_BAUD}.")
            return arduino_obj
        except Exception as exc:
            print(f"Could not connect to {port}: {exc}")

    print("Failed to connect to Arduino.")
    return None


def draw_hand_landmarks(frame: np.ndarray, lms: list, h: int, w: int) -> None:
    for start, end in HAND_CONNECTIONS:
        x1, y1 = int(lms[start].x * w), int(lms[start].y * h)
        x2, y2 = int(lms[end].x * w), int(lms[end].y * h)
        cv2.line(frame, (x1, y1), (x2, y2), (200, 200, 0), 2)
    for idx, lm in enumerate(lms):
        cx, cy = int(lm.x * w), int(lm.y * h)
        color = (0, 0, 255) if idx in (4, 8) else (0, 255, 0)
        cv2.circle(frame, (cx, cy), 6 if idx in (4, 8) else 4, color, -1)


def get_mouth_ratio(face_landmarks, h: int, w: int) -> tuple:
    upper_lip = face_landmarks[UPPER_LIP_IDX]
    lower_lip = face_landmarks[LOWER_LIP_IDX]
    forehead = face_landmarks[FOREHEAD_IDX]
    chin = face_landmarks[CHIN_IDX]
    
    ux, uy = int(upper_lip.x * w), int(upper_lip.y * h)
    lx, ly = int(lower_lip.x * w), int(lower_lip.y * h)
    
    face_height = abs(chin.y - forehead.y)
    if face_height < 0.01:
        face_height = 0.01
    
    mouth_open_dist = abs(lower_lip.y - upper_lip.y)
    mouth_ratio = mouth_open_dist / face_height
    
    return mouth_ratio, (ux, uy), (lx, ly)


def draw_mouth(frame: np.ndarray, face_landmarks, h: int, w: int, upper_pt, lower_pt) -> None:
    cv2.circle(frame, upper_pt, 8, (0, 255, 0), -1)
    cv2.circle(frame, lower_pt, 8, (0, 0, 255), -1)
    cv2.line(frame, upper_pt, lower_pt, (255, 0, 255), 2)
    
    for i in range(len(MOUTH_OUTLINE) - 1):
        idx1 = MOUTH_OUTLINE[i]
        idx2 = MOUTH_OUTLINE[i + 1]
        pt1 = face_landmarks[idx1]
        pt2 = face_landmarks[idx2]
        x1, y1 = int(pt1.x * w), int(pt1.y * h)
        x2, y2 = int(pt2.x * w), int(pt2.y * h)
        cv2.line(frame, (x1, y1), (x2, y2), (255, 200, 0), 1)


def main() -> None:
    global CONTROL_MODE
    
    # إعداد Hand Landmarker
    hand_options = mp_vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=HAND_MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    
    # إعداد Face Landmarker
    face_options = mp_vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=FACE_MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Could not open webcam.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    hand_value = 0
    mouth_value = 0
    output_value = 0
    last_sent_value = -1
    hand_dist = 0.0
    mouth_ratio = 0.0
    
    arduino = None
    serial_ok = False
    last_reconnect_try = 0.0
    last_serial_send_ts = 0.0
    frame_ts = 0
    
    print("=" * 60)
    print("Hand & Mouth Control System (Tasks API)")
    print(f"Control Mode: {CONTROL_MODE}")
    print("Press H = Hand only, M = Mouth only, B = Both")
    print("Press Q or ESC to exit.")
    print("=" * 60)

    if not SERIAL_ENABLED:
        print("Serial is disabled by config.")
    elif serial is None:
        print("pyserial is not installed.")
    else:
        print("Looking for Arduino...")
        arduino = connect_arduino(ARDUINO_PORT)
        if arduino is not None:
            serial_ok = True
        else:
            print("Not connected yet. Will retry every 5 seconds...")
    
    print("=" * 60)

    with mp_vision.HandLandmarker.create_from_options(hand_options) as hand_detector, \
         mp_vision.FaceLandmarker.create_from_options(face_options) as face_detector:
        
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Failed to read frame.")
                break

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            frame_ts += 33
            
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            
            hand_detected = False
            face_detected = False
            
            # ─── تتبع اليد ───
            if CONTROL_MODE in ("HAND", "BOTH"):
                hand_result = hand_detector.detect_for_video(mp_image, frame_ts)
                if hand_result.hand_landmarks:
                    hand_detected = True
                    hand_lms = hand_result.hand_landmarks[0]
                    
                    draw_hand_landmarks(frame, hand_lms, h, w)
                    
                    thumb_tip = hand_lms[4]
                    index_tip = hand_lms[8]
                    tx, ty = int(thumb_tip.x * w), int(thumb_tip.y * h)
                    ix, iy = int(index_tip.x * w), int(index_tip.y * h)
                    hand_dist = math.hypot(ix - tx, iy - ty)
                    hand_value = hand_dist_to_value(hand_dist)
                    
                    cv2.line(frame, (tx, ty), (ix, iy), (255, 100, 0), 3)
                    mid = ((tx + ix) // 2, (ty + iy) // 2)
                    cv2.putText(frame, f"{hand_dist:.0f}px", mid,
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 100, 0), 2)
            
            # ─── تتبع الوجه/الفم ───
            if CONTROL_MODE in ("MOUTH", "BOTH"):
                face_result = face_detector.detect_for_video(mp_image, frame_ts)
                if face_result.face_landmarks:
                    face_detected = True
                    face_lms = face_result.face_landmarks[0]
                    
                    mouth_ratio, upper_pt, lower_pt = get_mouth_ratio(face_lms, h, w)
                    mouth_value = mouth_ratio_to_value(mouth_ratio)
                    draw_mouth(frame, face_lms, h, w, upper_pt, lower_pt)
            
            # ─── تحديد قيمة الخرج ───
            if CONTROL_MODE == "HAND":
                output_value = hand_value if hand_detected else 0
            elif CONTROL_MODE == "MOUTH":
                output_value = mouth_value if face_detected else 0
            elif CONTROL_MODE == "BOTH":
                if hand_detected and face_detected:
                    output_value = max(hand_value, mouth_value)
                elif hand_detected:
                    output_value = hand_value
                elif face_detected:
                    output_value = mouth_value
                else:
                    output_value = 0
            
            # ─── محاولة إعادة الاتصال ───
            if SERIAL_ENABLED and serial is not None and arduino is None:
                now = time.monotonic()
                if now - last_reconnect_try >= ARDUINO_RECONNECT_SEC:
                    last_reconnect_try = now
                    arduino = connect_arduino(ARDUINO_PORT)
                    serial_ok = arduino is not None
            
            # ─── إرسال القيمة للأردوينو ───
            if arduino is not None:
                now_send = time.monotonic()
                should_send = (
                    abs(output_value - last_sent_value) >= SERIAL_MIN_DELTA
                    and (now_send - last_serial_send_ts) >= SERIAL_SEND_INTERVAL_SEC
                )
                if should_send:
                    if send_value(arduino, output_value):
                        last_sent_value = output_value
                        last_serial_send_ts = now_send
                    else:
                        serial_ok = False
                        arduino = None
            
            # ─── شريط تمثيل القيمة ───
            bar_w = int((output_value / MAX_VALUE) * (w - 40))
            cv2.rectangle(frame, (20, h - 50), (w - 20, h - 30), (50, 50, 50), -1)
            cv2.rectangle(frame, (20, h - 50), (20 + bar_w, h - 30), (0, 255, 100), -1)

            # ─── نصوص المعلومات ───
            mode_colors = {"HAND": (0, 255, 255), "MOUTH": (255, 0, 255), "BOTH": (0, 255, 0)}
            cv2.putText(frame, f"Mode: {CONTROL_MODE}", (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, mode_colors[CONTROL_MODE], 2, cv2.LINE_AA)
            
            if CONTROL_MODE in ("HAND", "BOTH"):
                status = "OK" if hand_detected else "---"
                cv2.putText(frame, f"Hand: {hand_value} ({status})", (20, 70),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            
            if CONTROL_MODE in ("MOUTH", "BOTH"):
                status = "OK" if face_detected else "---"
                cv2.putText(frame, f"Mouth: {mouth_value} ({status})", (20, 100),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 255), 2, cv2.LINE_AA)
            
            cv2.putText(frame, f"Output: {output_value}", (20, 135),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Pin: {ARDUINO_PIN}", (20, 165),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)
            
            serial_text = "Serial: OK" if serial_ok and arduino is not None else "Serial: OFF"
            serial_color = (0, 220, 0) if serial_ok and arduino is not None else (0, 0, 255)
            cv2.putText(frame, serial_text, (20, 195),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, serial_color, 2, cv2.LINE_AA)
            
            active_port = arduino.port if arduino is not None else "N/A"
            cv2.putText(frame, f"Port: {active_port}", (20, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 220, 255), 2, cv2.LINE_AA)
            
            cv2.putText(frame, "H=Hand  M=Mouth  B=Both  Q=Quit",
                        (10, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow("Hand & Mouth Control", frame)
            key = cv2.waitKey(1) & 0xFF
            
            if key in (ord("q"), 27):
                break
            elif key == ord("h"):
                CONTROL_MODE = "HAND"
                print("Mode: HAND only")
            elif key == ord("m"):
                CONTROL_MODE = "MOUTH"
                print("Mode: MOUTH only")
            elif key == ord("b"):
                CONTROL_MODE = "BOTH"
                print("Mode: BOTH (Hand + Mouth)")

    cap.release()
    cv2.destroyAllWindows()
    if arduino is not None and arduino.is_open:
        arduino.close()
    
    print("Program closed.")


if __name__ == "__main__":
    main()
