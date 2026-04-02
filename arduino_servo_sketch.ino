/*
 * Servo Motor Control via Serial
 * التحكم بسيرفو موتور عبر الاتصال التسلسلي
 * 
 * يستقبل زاوية (0-180) من Python عبر Serial
 * ويحركها السيرفو مباشرة
 * 
 * التوصيل:
 * - السيرفو إشارة (برتقالي/أصفر) → Pin 9
 * - السيرفو VCC (أحمر) → 5V
 * - السيرفو GND (بني/أسود) → GND
 * 
 * ملاحظة: إذا كان السيرفو كبير، استخدم مصدر طاقة خارجي
 */

#include <Servo.h>

Servo myServo;
const int SERVO_PIN = 9;

String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(9600);
  myServo.attach(SERVO_PIN);
  myServo.write(0);  // البداية من زاوية 0
  
  Serial.println("Servo Control Ready");
  Serial.println("Send angle (0-180) to control servo");
}

void loop() {
  // قراءة البيانات من Serial
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
  
  // معالجة الزاوية المستلمة
  if (stringComplete) {
    inputString.trim();
    int angle = inputString.toInt();
    
    // التأكد من أن الزاوية في النطاق الصحيح
    angle = constrain(angle, 0, 180);
    
    // تحريك السيرفو
    myServo.write(angle);
    
    // طباعة للتأكيد (اختياري)
    // Serial.print("Angle: ");
    // Serial.println(angle);
    
    // إعادة تعيين المتغيرات
    inputString = "";
    stringComplete = false;
  }
}
