// =============================================
// 차단기 제어 코드
//
// 서보모터     → 9번 핀
// 입구 초음파  → TRIG:4, ECHO:5 (뒤차 감지)
// 출구 초음파  → TRIG:6, ECHO:7 (출차 감지)
//
// 동작:
// 'O\n' 신호 → 45도 올라감
// 입구 초음파 감지 → 차단기 계속 올라가있음
// 입구 초음파 감지 안됨 + 10초 경과 → 차단기 내려옴
// 출구 초음파 감지 → 45도 올라감 → 10초 후 내려옴
// =============================================

#include <Servo.h>

// 핀 설정
const int SERVO_PIN  = 9;
const int ENTRY_TRIG = 4;
const int ENTRY_ECHO = 5;
const int EXIT_TRIG  = 6;
const int EXIT_ECHO  = 7;

// 차단기 각도
const int GATE_CLOSE = 0;
const int GATE_OPEN  = 90;

// 거리 설정 (cm)
const int ENTRY_DETECT = 5;  // 입구 뒤차 감지 거리
const int EXIT_DETECT  = 5;  // 출구 차량 감지 거리

// 차단기 기본 열림 시간 (ms) - 뒤차 없을 때
const unsigned long GATE_OPEN_TIME = 5000;  // 5초

// 출구 쿨타임 (ms)
const unsigned long EXIT_COOLDOWN = 5000;

// 상태 변수
bool gateIsOpen          = false;
unsigned long gateOpenedAt   = 0;
unsigned long lastExitOpen   = 0;

Servo gateServo;
String inputBuffer = "";

void setup() {
    Serial.begin(9600);

    gateServo.attach(SERVO_PIN);
    gateServo.write(GATE_CLOSE);
    delay(500);
    gateServo.detach();
    gateIsOpen = false;

    pinMode(ENTRY_TRIG, OUTPUT);
    pinMode(ENTRY_ECHO, INPUT);
    pinMode(EXIT_TRIG, OUTPUT);
    pinMode(EXIT_ECHO, INPUT);

    Serial.println("Gate system ready");
}

void loop() {
    unsigned long now = millis();

    // ── 1. 파이썬 신호 수신 ──────────────────────────────
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            inputBuffer.trim();
            if (inputBuffer == "O") {
                Serial.println("Gate open signal received");
                openGate(now);
            }
            inputBuffer = "";
        } else {
            inputBuffer += c;
        }
    }

    // ── 2. 차단기 열려있을 때 체크 ───────────────────────
    if (gateIsOpen) {
        int entryDist = getDistance(ENTRY_TRIG, ENTRY_ECHO);
        bool rearCarDetected = (entryDist > 0 && entryDist < ENTRY_DETECT);

        if (rearCarDetected) {
            // 뒤차 감지됨 → 타이머 계속 리셋 (차단기 계속 올라가있음)
            gateOpenedAt = now;
            Serial.print("Rear car detected (");
            Serial.print(entryDist);
            Serial.println("cm) - keeping gate open");
        } else {
            // 뒤차 없음 → 10초 지나면 자동으로 닫기
            if (now - gateOpenedAt >= GATE_OPEN_TIME) {
                Serial.println("No rear car - closing gate");
                closeGate();
            }
        }
    }

    // ── 3. 출구 초음파 - 출차 차량 감지 ─────────────────
    if (!gateIsOpen && now - lastExitOpen > EXIT_COOLDOWN) {
        int exitDist = getDistance(EXIT_TRIG, EXIT_ECHO);
        if (exitDist > 0 && exitDist < EXIT_DETECT) {
            Serial.print("Exit vehicle detected (");
            Serial.print(exitDist);
            Serial.println("cm) - opening gate");
            openGate(now);
            lastExitOpen = now;
        }
    }

    delay(50);
}

// 차단기 열기
void openGate(unsigned long now) {
    gateServo.attach(SERVO_PIN);
    gateServo.write(GATE_OPEN);
    gateIsOpen   = true;
    gateOpenedAt = now;
    Serial.println("Gate opened (45 degrees)");
}

// 차단기 닫기
void closeGate() {
    gateServo.write(GATE_CLOSE);
    delay(500);
    gateServo.detach();
    gateIsOpen = false;
    Serial.println("Gate closed");
}

// 초음파 거리 측정
int getDistance(int trigPin, int echoPin) {
    digitalWrite(trigPin, LOW);
    delayMicroseconds(2);
    digitalWrite(trigPin, HIGH);
    delayMicroseconds(10);
    digitalWrite(trigPin, LOW);

    long duration = pulseIn(echoPin, HIGH, 30000);
    if (duration == 0) return -1;

    return duration * 0.034 / 2;
}
