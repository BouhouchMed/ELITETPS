# مشروع التحكم بالحركة - Hand & Mouth Control
## التحكم بالأردوينو باستخدام حركة اليد والفم

---

## 📋 محتويات المشروع

| الملف | الوصف |
|-------|-------|
| `hand_distance_x.py` | التحكم بـ LED باستخدام المسافة بين الأصابع |
| `hand_mouth_control.py` | التحكم باليد والفم معاً (للسيرفو) |
| `mouth_servo_control.py` | التحكم بالسيرفو بالفم فقط |
| `arduino_led_sketch.ino` | كود Arduino لـ LED |
| `arduino_servo_sketch.ino` | كود Arduino للسيرفو |
| `hand_landmarker.task` | نموذج تعرف اليد |
| `face_landmarker.task` | نموذج تعرف الوجه |

---

## 🔧 المتطلبات

### البرامج:
- Python 3.10 أو أحدث (يفضل 3.11 أو 3.12)
- Arduino IDE

### الأجهزة:
- كاميرا ويب (Webcam)
- Arduino Uno أو Nano
- LED + مقاومة 220Ω (لمشروع LED)
- سيرفو موتور SG90 (لمشروع السيرفو)

---

## 📥 خطوات التثبيت

### 1. تثبيت Python
حمّل Python من: https://www.python.org/downloads/
⚠️ **مهم:** اختر "Add Python to PATH" أثناء التثبيت

### 2. تثبيت المكتبات
افتح Command Prompt (أو PowerShell) في مجلد المشروع واكتب:

```
pip install -r requirements.txt
```

أو ثبّت كل مكتبة على حدة:

```
pip install opencv-python mediapipe numpy pyserial
```

### 3. رفع كود Arduino
- افتح Arduino IDE
- افتح الملف المناسب:
  - `arduino_led_sketch.ino` للتحكم بـ LED
  - `arduino_servo_sketch.ino` للتحكم بالسيرفو
- اختر البورد والمنفذ الصحيح
- اضغط Upload

---

## 🔌 التوصيلات

### مشروع LED (hand_distance_x.py):
```
Arduino Pin 10 ──→ LED (+) الطرف الطويل
LED (-) ──→ مقاومة 220Ω ──→ GND
```

### مشروع السيرفو (mouth_servo_control.py / hand_mouth_control.py):
```
Arduino Pin 9 ──→ سلك الإشارة (برتقالي/أصفر)
Arduino 5V ──→ سلك الطاقة (أحمر)
Arduino GND ──→ سلك الأرضي (بني/أسود)
```

---

## ▶️ التشغيل

### التحكم بـ LED باليد:
```
python hand_distance_x.py
```
- قرّب/بعّد الإبهام من السبابة للتحكم بشدة الإضاءة

### التحكم بالسيرفو بالفم:
```
python mouth_servo_control.py
```
- افتح فمك للتحكم بزاوية السيرفو (0-180°)

### التحكم باليد والفم معاً:
```
python hand_mouth_control.py
```
- اضغط **H** = وضع اليد فقط
- اضغط **M** = وضع الفم فقط
- اضغط **B** = كلاهما (القيمة الأكبر)
- اضغط **Q** = خروج

---

## ⚙️ تعديل الإعدادات

افتح ملف Python وعدّل الثوابت في أعلى الملف:

```python
ARDUINO_PORT = "COM7"      # غيّره لرقم المنفذ عندك
CAMERA_WIDTH = 1280        # دقة الكاميرا
CAMERA_HEIGHT = 720
MIN_DIST = 10.0            # أقل مسافة بين الأصابع
MAX_DIST = 200.0           # أكبر مسافة
```

### معرفة رقم المنفذ:
1. افتح Device Manager
2. ابحث عن "Ports (COM & LPT)"
3. ستجد Arduino على منفذ مثل COM3 أو COM7

---

## ❓ حل المشاكل الشائعة

### "Could not open webcam"
- تأكد أن الكاميرا متصلة ولا يستخدمها برنامج آخر

### "pyserial is not installed"
```
pip install pyserial
```

### "Failed to connect to Arduino"
- تأكد من رقم المنفذ COM
- أغلق Arduino IDE Serial Monitor
- جرب فصل وتوصيل USB

### الشاشة بطيئة
عدّل في الملف:
```python
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
```

---

## 📚 كيف يعمل المشروع؟

1. **الكاميرا** تلتقط صورة الفيديو
2. **MediaPipe** يكتشف اليد/الوجه ويحدد النقاط
3. **Python** يحسب المسافة/نسبة فتح الفم
4. **Serial** يرسل القيمة للأردوينو
5. **Arduino** يتحكم بـ LED/السيرفو

---

## 👨‍🏫 معلومات إضافية

- تم تطوير المشروع باستخدام MediaPipe Tasks API
- يعمل على Windows 10/11
- يدعم Python 3.10+

**استمتع بالتعلم! 🚀**
