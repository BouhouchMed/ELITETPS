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

# ─── مسار النموذج (نسبي للمجلد الحالي) ───
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FACE_MODEL_PATH = os.path.join(SCRIPT_DIR, "face_landmarker.task")

# ─── إعدادات نطاق فتحة الفم → زاوية السيرفو ───
MIN_MOUTH_RATIO = 0.02   # فم مغلق
MAX_MOUTH_RATIO = 0.15   # فم مفتوح بالكامل
MIN_ANGLE = 0            # زاوية السيرفو عند إغلاق الفم
MAX_ANGLE = 180          # زاوية السيرفو عند فتح الفم

# ─── إعدادات الاتصال مع Arduino ───
ARDUINO_PORT = "COM7"
ARDUINO_BAUD = 9600
ARDUINO_SERVO_PIN = 9
ARDUINO_BOOT_WAIT_SEC = 2.5
ARDUINO_RECONNECT_SEC = 5.0
SERIAL_ENABLED = True

# ─── إعدادات الكاميرا والأداء ───
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
SERIAL_SEND_INTERVAL_SEC = 0.03
SERIAL_MIN_DELTA_ANGLE = 2

# ─── نقاط الفم في Face Landmarker (478 نقطة) ───
UPPER_LIP_IDX = 13
LOWER_LIP_IDX = 14
FOREHEAD_IDX = 10
CHIN_IDX = 152

# نقاط محيط الفم للرسم
MOUTH_OUTLINE = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
                 78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def mouth_ratio_to_angle(ratio: float) -> int:
    """تحويل نسبة فتحة الفم إلى زاوية سيرفو (0-180)."""
    ratio = clamp(ratio, MIN_MOUTH_RATIO, MAX_MOUTH_RATIO)
    normalized = (ratio - MIN_MOUTH_RATIO) / (MAX_MOUTH_RATIO - MIN_MOUTH_RATIO)
    return int(normalized * (MAX_ANGLE - MIN_ANGLE) + MIN_ANGLE)


def send_angle(arduino_obj, angle: int) -> bool:
    """إرسال زاوية السيرفو كنص ASCII."""
    try:
        arduino_obj.write(f"{angle}\n".encode("ascii"))
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


def get_mouth_ratio(face_landmarks, h: int, w: int) -> tuple:
    """حساب نسبة فتحة الفم من نقاط الوجه."""
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


def draw_face_landmarks(frame: np.ndarray, face_landmarks, h: int, w: int, upper_pt, lower_pt) -> None:
    """رسم نقاط الوجه والفم."""
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
        cv2.line(frame, (x1, y1), (x2, y2), (255, 200, 0), 2)
    
    key_points = [10, 152, 234, 454, 1, 4]
    for idx in key_points:
        pt = face_landmarks[idx]
        x, y = int(pt.x * w), int(pt.y * h)
        cv2.circle(frame, (x, y), 3, (100, 255, 100), -1)


def main() -> None:
    options = mp_vision.FaceLandmarkerOptions(
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
    
    mouth_ratio = 0.0
    servo_angle = 0
    last_sent_angle = -1
    arduino = None
    serial_ok = False
    last_reconnect_try = 0.0
    last_serial_send_ts = 0.0
    frame_ts = 0
    
    print("=" * 60)
    print("Mouth-Controlled Servo Motor")
    print("افتح فمك للتحكم بزاوية السيرفو (0-180)")
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

    with mp_vision.FaceLandmarker.create_from_options(options) as detector:
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
            result = detector.detect_for_video(mp_image, frame_ts)

            if SERIAL_ENABLED and serial is not None and arduino is None:
                now = time.monotonic()
                if now - last_reconnect_try >= ARDUINO_RECONNECT_SEC:
                    last_reconnect_try = now
                    arduino = connect_arduino(ARDUINO_PORT)
                    serial_ok = arduino is not None

            if result.face_landmarks:
                face_lms = result.face_landmarks[0]
                
                mouth_ratio, upper_pt, lower_pt = get_mouth_ratio(face_lms, h, w)
                servo_angle = mouth_ratio_to_angle(mouth_ratio)
                
                draw_face_landmarks(frame, face_lms, h, w, upper_pt, lower_pt)
                
                if arduino is not None:
                    now_send = time.monotonic()
                    should_send = (
                        abs(servo_angle - last_sent_angle) >= SERIAL_MIN_DELTA_ANGLE
                        and (now_send - last_serial_send_ts) >= SERIAL_SEND_INTERVAL_SEC
                    )
                    if should_send:
                        if send_angle(arduino, servo_angle):
                            last_sent_angle = servo_angle
                            last_serial_send_ts = now_send
                        else:
                            serial_ok = False
                            arduino = None
            else:
                mouth_ratio = 0.0
                servo_angle = 0
                if arduino is not None:
                    now_send = time.monotonic()
                    should_send = (
                        abs(servo_angle - last_sent_angle) >= SERIAL_MIN_DELTA_ANGLE
                        and (now_send - last_serial_send_ts) >= SERIAL_SEND_INTERVAL_SEC
                    )
                    if should_send:
                        if send_angle(arduino, servo_angle):
                            last_sent_angle = servo_angle
                            last_serial_send_ts = now_send
                        else:
                            serial_ok = False
                            arduino = None

            bar_w = int((servo_angle / MAX_ANGLE) * (w - 40))
            cv2.rectangle(frame, (20, h - 50), (w - 20, h - 30), (50, 50, 50), -1)
            cv2.rectangle(frame, (20, h - 50), (20 + bar_w, h - 30), (0, 255, 100), -1)

            cv2.putText(frame, f"Mouth Ratio = {mouth_ratio:.3f}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Servo Angle = {servo_angle} deg", (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 220, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, f"Servo Pin = {ARDUINO_SERVO_PIN}", (20, 115),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2, cv2.LINE_AA)
            
            serial_text = "Serial: OK" if serial_ok and arduino is not None else "Serial: OFF"
            serial_color = (0, 220, 0) if serial_ok and arduino is not None else (0, 0, 255)
            cv2.putText(frame, serial_text, (20, 150),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, serial_color, 2, cv2.LINE_AA)
            
            active_port = arduino.port if arduino is not None else "N/A"
            cv2.putText(frame, f"Port: {active_port}", (20, 185),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 220, 255), 2, cv2.LINE_AA)
            
            cv2.putText(frame, "Open mouth to control servo",
                        (10, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            cv2.putText(frame, "Q / ESC = quit",
                        (w - 160, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow("Mouth -> Servo Control", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break

    cap.release()
    cv2.destroyAllWindows()
    if arduino is not None and arduino.is_open:
        arduino.close()
    
    print("Program closed.")


if __name__ == "__main__":
    main()
