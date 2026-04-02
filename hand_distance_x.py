import ctypes

# Fix: mediapipe shared lib does not export 'free' on Windows (Python 3.13)
# We intercept CDLL.__getitem__ to redirect 'free' to ucrtbase.dll
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

# مسار النموذج (نسبي للمجلد الحالي)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "hand_landmarker.task")

# â”€â”€ Ù†Ù‚Ø§Ø· Ø§Ù„Ù…ÙØ§ØµÙ„ Ø§Ù„Ù€ 21
# 0: WRIST  1-4: THUMB  5-8: INDEX  9-12: MIDDLE  13-16: RING  17-20: PINKY
LANDMARK_NAMES = [
    "WRIST",
    "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP",
    "INDEX_MCP", "INDEX_PIP", "INDEX_DIP", "INDEX_TIP",
    "MIDDLE_MCP", "MIDDLE_PIP", "MIDDLE_DIP", "MIDDLE_TIP",
    "RING_MCP", "RING_PIP", "RING_DIP", "RING_TIP",
    "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP",
]

# HAND_CONNECTIONS Ù„Ø±Ø³Ù… Ø®Ø·ÙˆØ· Ø±Ø¨Ø· Ø§Ù„Ù…ÙØ§ØµÙ„
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),       # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),       # index
    (0, 9), (9, 10), (10, 11), (11, 12),  # middle
    (0, 13), (13, 14), (14, 15), (15, 16),# ring
    (0, 17), (17, 18), (18, 19), (19, 20),# pinky
    (5, 9), (9, 13), (13, 17),            # palm
]

# Ù†Ø·Ø§Ù‚ Ø§Ù„Ù…Ø³Ø§ÙØ© (Ø¨ÙƒØ³Ù„) â†’ x Ø¨ÙŠÙ† 0 Ùˆ 100
MIN_DIST = 10.0
MAX_DIST = 200.0
MIN_X = 0.0
MAX_X = 100.0

# Ø¥Ø¹Ø¯Ø§Ø¯Ø§Øª Ø§Ù„Ø§ØªØµØ§Ù„ Ù…Ø¹ Arduino
# Ø¶Ø¹ None Ù„Ø§Ø®ØªÙŠØ§Ø± Ø§Ù„Ù…Ù†ÙØ° ØªÙ„Ù‚Ø§Ø¦ÙŠÙ‹Ø§ØŒ Ø£Ùˆ Ø§ÙƒØªØ¨ Ù…Ø«Ù„ "COM7"
ARDUINO_PORT = "COM7"
ARDUINO_BAUD = 9600
ARDUINO_LED_PIN = 10
ARDUINO_BOOT_WAIT_SEC = 2.5
ARDUINO_RECONNECT_SEC = 5.0
SERIAL_ENABLED = True
FORCE_LED_OFF = False

# Performance optimization
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 720
FRAME_SKIP = 0  # run inference every frame for best accuracy
SERIAL_SEND_INTERVAL_SEC = 0.04
SERIAL_MIN_DELTA_PWM = 2


def x_to_pwm(x_value: float) -> int:
    """Ø­ÙˆÙ‘Ù„ x Ù…Ù† Ø§Ù„Ù…Ø¬Ø§Ù„ [0..100] Ø¥Ù„Ù‰ PWM [0..255]."""
    x_value = clamp(x_value, MIN_X, MAX_X)
    return int((x_value / MAX_X) * 255)


def send_pwm(arduino_obj, pwm: int) -> bool:
    """Send PWM value as ASCII line and return success state."""
    try:
        arduino_obj.write(f"{pwm}\n".encode("ascii"))
        return True
    except Exception as exc:
        print(f"Serial write failed: {exc}")
        return False


def detect_arduino_port(preferred_port: str | None = None) -> str | None:
    """Return a likely Arduino COM port, preferring configured port if provided."""
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
    """Try to connect to Arduino and return serial object or None."""
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
            # Arduino ØºØ§Ù„Ø¨Ù‹Ø§ ÙŠØ¹ÙŠØ¯ Ø§Ù„ØªØ´ØºÙŠÙ„ Ø¹Ù†Ø¯ ÙØªØ­ Ø§Ù„Ù…Ù†ÙØ° Ø§Ù„ØªØ³Ù„Ø³Ù„ÙŠ.
            time.sleep(ARDUINO_BOOT_WAIT_SEC)
            # ØªÙØ±ÙŠØº Ø£ÙŠ Ø¨ÙŠØ§Ù†Ø§Øª Ø¹Ø§Ù„Ù‚Ø© Ù…Ù† Ø§Ù„Ø§ØªØµØ§Ù„ Ø§Ù„Ø³Ø§Ø¨Ù‚
            arduino_obj.reset_input_buffer()
            arduino_obj.reset_output_buffer()
            arduino_obj.flush()
            print(f"Arduino connected on {port} @ {ARDUINO_BAUD}.")
            return arduino_obj
        except Exception as exc:
            print(f"Could not connect to {port}: {exc}")

    print("Failed to connect to Arduino on all candidate ports.")
    return None


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def scale_to_x(distance: float) -> float:
    distance = clamp(distance, MIN_DIST, MAX_DIST)
    return (distance - MIN_DIST) / (MAX_DIST - MIN_DIST) * (MAX_X - MIN_X) + MIN_X


def draw_landmarks(frame: np.ndarray, lms: list, h: int, w: int) -> None:
    for start, end in HAND_CONNECTIONS:
        x1, y1 = int(lms[start].x * w), int(lms[start].y * h)
        x2, y2 = int(lms[end].x * w), int(lms[end].y * h)
        cv2.line(frame, (x1, y1), (x2, y2), (200, 200, 0), 2)
    for idx, lm in enumerate(lms):
        cx, cy = int(lm.x * w), int(lm.y * h)
        color = (0, 0, 255) if idx in (4, 8) else (0, 255, 0)
        cv2.circle(frame, (cx, cy), 6 if idx in (4, 8) else 4, color, -1)




def main() -> None:
    options = mp_vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("Could not open webcam.")
        return

    # Lower camera latency and reduce processing load.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    x = 0.0
    brightness_x = 0.0
    pwm_value = 0
    last_sent_pwm = -1
    arduino = None
    serial_ok = False
    last_reconnect_try = 0.0
    frame_ts = 0
    frame_count = 0
    last_serial_send_ts = 0.0
    last_result = None
    print("Running hand joint tracking. Press Q or ESC to exit.")
    print("=" * 60)

    if not SERIAL_ENABLED:
        print("Serial is disabled by config.")
    elif serial is None:
        print("pyserial is not installed. Arduino control disabled.")
        print("Install: pip install pyserial")
    else:
        print("Looking for Arduino...")
        available = list_available_ports()
        if available:
            print(f"Available COM ports: {', '.join(available)}")
        else:
            print("No COM ports found. Check USB connection.")
        
        arduino = connect_arduino(ARDUINO_PORT)
        if arduino is not None:
            serial_ok = True
        else:
            print("Not connected yet. Will retry every 5 seconds...")
    
    print("=" * 60)

    with mp_vision.HandLandmarker.create_from_options(options) as detector:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Failed to read frame.")
                break

            frame_count += 1

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            frame_ts += 33  # ~30 fps timestamp in ms

            do_inference = (FRAME_SKIP == 0) or (frame_count % (FRAME_SKIP + 1) == 0)
            if do_inference:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = detector.detect_for_video(mp_image, frame_ts)
                last_result = result
            else:
                result = last_result

            # Ù…Ø­Ø§ÙˆÙ„Ø© Ø¥Ø¹Ø§Ø¯Ø© Ø§Ù„Ø§ØªØµØ§Ù„ ØªÙ„Ù‚Ø§Ø¦ÙŠÙ‹Ø§ Ø¹Ù†Ø¯ Ø§Ù†Ù‚Ø·Ø§Ø¹ Ø§Ù„Ø³ÙŠØ±ÙŠØ§Ù„.
            if SERIAL_ENABLED and serial is not None and arduino is None:
                now = time.monotonic()
                if now - last_reconnect_try >= ARDUINO_RECONNECT_SEC:
                    last_reconnect_try = now
                    arduino = connect_arduino(ARDUINO_PORT)
                    serial_ok = arduino is not None

            if result is not None and result.hand_landmarks:
                lms = result.hand_landmarks[0]
                draw_landmarks(frame, lms, h, w)

                # â”€â”€ Ø­Ø³Ø§Ø¨ Ø§Ù„Ù…Ø³Ø§ÙØ© Ø¨ÙŠÙ† Ø·Ø±Ù Ø§Ù„Ø¥Ø¨Ù‡Ø§Ù… (4) ÙˆØ·Ø±Ù Ø§Ù„Ø³Ø¨Ø§Ø¨Ø© (8)
                tx, ty = int(lms[4].x * w), int(lms[4].y * h)
                ix, iy = int(lms[8].x * w), int(lms[8].y * h)
                dist = math.hypot(ix - tx, iy - ty)
                x = scale_to_x(dist)
                # Ø±Ø¨Ø· Ù…ØªØºÙŠØ± Ø§Ù„Ø¥Ø¶Ø§Ø¡Ø© Ù…Ø¨Ø§Ø´Ø±Ø© Ù…Ø¹ x (0..100)
                brightness_x = x
                pwm_value = x_to_pwm(brightness_x)

                if FORCE_LED_OFF:
                    brightness_x = 0.0
                    pwm_value = 0

                # â”€â”€ Ø®Ø· Ø§Ù„Ù…Ø³Ø§ÙØ©
                mid = ((tx + ix) // 2, (ty + iy) // 2)
                cv2.line(frame, (tx, ty), (ix, iy), (255, 100, 0), 2)
                cv2.putText(frame, f"{dist:.0f}px", mid,
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 100, 0), 2)

                if arduino is not None:
                    now_send = time.monotonic()
                    should_send = (
                        abs(pwm_value - last_sent_pwm) >= SERIAL_MIN_DELTA_PWM
                        and (now_send - last_serial_send_ts) >= SERIAL_SEND_INTERVAL_SEC
                    )
                    if should_send:
                        if send_pwm(arduino, pwm_value):
                            last_sent_pwm = pwm_value
                            last_serial_send_ts = now_send
                        else:
                            serial_ok = False
                            arduino = None
            else:
                # Ø¨Ø¯ÙˆÙ† ÙŠØ¯: Ø¥Ø¹Ø§Ø¯Ø© Ø§Ù„Ø¥Ø¶Ø§Ø¡Ø© Ø¥Ù„Ù‰ 0 ÙˆØ¥Ø±Ø³Ø§Ù„Ù‡Ø§ Ù„Ù„Ø£Ø±Ø¯ÙˆÙŠÙ†Ùˆ.
                x = 0.0
                brightness_x = 0.0
                pwm_value = 0
                if arduino is not None:
                    now_send = time.monotonic()
                    should_send = (
                        abs(pwm_value - last_sent_pwm) >= SERIAL_MIN_DELTA_PWM
                        and (now_send - last_serial_send_ts) >= SERIAL_SEND_INTERVAL_SEC
                    )
                    if should_send:
                        if send_pwm(arduino, pwm_value):
                            last_sent_pwm = pwm_value
                            last_serial_send_ts = now_send
                        else:
                            serial_ok = False
                            arduino = None

            # â”€â”€ Ø´Ø±ÙŠØ· ØªÙ…Ø«ÙŠÙ„ x
            bar_w = int((x / MAX_X) * (w - 40))
            cv2.rectangle(frame, (20, h - 50), (w - 20, h - 30), (50, 50, 50), -1)
            cv2.rectangle(frame, (20, h - 50), (20 + bar_w, h - 30), (0, 220, 255), -1)

            # â”€â”€ Ù†ØµÙˆØµ Ø§Ù„Ù…Ø¹Ù„ÙˆÙ…Ø§Øª
            cv2.putText(frame, f"x = {x:.1f}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3, cv2.LINE_AA)
            cv2.putText(frame, f"Brightness = {brightness_x:.1f}", (20, 75),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 220, 0), 2, cv2.LINE_AA)
            cv2.putText(frame, f"LED pwm({ARDUINO_LED_PIN}) = {pwm_value}", (20, 105),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2, cv2.LINE_AA)
            if FORCE_LED_OFF:
                cv2.putText(frame, "LED MODE: OFF", (20, 165),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
            serial_text = "Serial: OK" if serial_ok and arduino is not None else "Serial: OFF"
            serial_color = (0, 220, 0) if serial_ok and arduino is not None else (0, 0, 255)
            cv2.putText(frame, serial_text, (20, 135),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, serial_color, 2, cv2.LINE_AA)
            active_port = arduino.port if arduino is not None else "N/A"
            cv2.putText(frame, f"Port: {active_port}", (20, 195),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (180, 220, 255), 2, cv2.LINE_AA)
            cv2.putText(frame, "Thumb(4) <-> Index(8) distance",
                        (10, h - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            cv2.putText(frame, "Q / ESC = quit",
                        (w - 160, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow("Hand Joints -> x (0-100)", frame)
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

