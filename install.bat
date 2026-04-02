@echo off
chcp 65001 >nul
echo ══════════════════════════════════════════════════════════
echo    تثبيت مشروع التحكم بالحركة
echo    Hand Control Project Installation
echo ══════════════════════════════════════════════════════════
echo.

echo [1/3] التحقق من Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python غير مثبت! حمّله من: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo ✓ Python متوفر

echo.
echo [2/3] تثبيت المكتبات المطلوبة...
pip install -r requirements.txt

echo.
echo [3/3] التحقق من الملفات...
if exist "hand_landmarker.task" (
    echo ✓ نموذج اليد موجود
) else (
    echo ❌ نموذج اليد غير موجود!
)

if exist "face_landmarker.task" (
    echo ✓ نموذج الوجه موجود
) else (
    echo ❌ نموذج الوجه غير موجود!
)

echo.
echo ══════════════════════════════════════════════════════════
echo    اكتمل التثبيت!
echo    Installation Complete!
echo ══════════════════════════════════════════════════════════
echo.
echo للتشغيل:
echo   python hand_distance_x.py      (التحكم بLED باليد)
echo   python mouth_servo_control.py  (التحكم بالسيرفو بالفم)
echo   python hand_mouth_control.py   (التحكم باليد والفم معاً)
echo.
pause
