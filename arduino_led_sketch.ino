/*
 * التحكم بـ LED عبر Serial
 * يستقبل قيمة PWM (0-255) من Python
 * 
 * التوصيل:
 * - LED (+) الطرف الطويل → Pin 10
 * - LED (-) → مقاومة 220Ω → GND
 */

const int LED_PIN = 10;
String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(9600);
  pinMode(LED_PIN, OUTPUT);
  analogWrite(LED_PIN, 0);
  Serial.println("LED Control Ready");
}

void loop() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
  
  if (stringComplete) {
    inputString.trim();
    int pwmValue = inputString.toInt();
    pwmValue = constrain(pwmValue, 0, 255);
    analogWrite(LED_PIN, pwmValue);
    
    inputString = "";
    stringComplete = false;
  }
}
