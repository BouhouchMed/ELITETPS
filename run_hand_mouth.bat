@echo off
chcp 65001 >nul
echo بدء تشغيل التحكم باليد والفم معاً...
echo H = يد فقط، M = فم فقط، B = كلاهما، Q = خروج
python hand_mouth_control.py
pause
