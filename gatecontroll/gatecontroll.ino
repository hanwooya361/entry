// =============================================
// 차단기 제어 코드
//
// 서보모터     → 9번 핀
// 입구 초음파  → TRIG:4, ECHO:5 (뒤차 감지)
// 출구 초음파  → TRIG:6, ECHO:7 (출차 감지)
//
// 동작:
// 'O\n' 신호 → 90도 천천히 올라감
// 뒤차 없음 + 5초 경과 → 천천히 내려오기 시작
// 내려오는 도중 초음파 감지 → 즉시 멈추고 다시 올라감
// 출구 초음파 감지 → 90도 올라감 → 5초 후 내려옴
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

// 서보모터 속도 설정 (클수록 느림)
const int SERVO_SPEED = 15;  // ms per degree

// 거리 설정 (cm)
const int ENTRY_DETECT = 5;
const int EXIT_DETECT  = 5;

// 차단기 열림 시간 (ms)
const unsigned long GATE_OPEN_TIME = 5000;  // 5초

// 출구 쿨타임 (ms)
const unsigned long EXIT_COOLDOWN = 5000;

// 상태 변수
bool gateIsOpen            = false;
unsigned long gateOpenedAt = 0;
unsigned long lastExitOpen = 0;
int currentAngle           = 0;

Servo gateServo;
String inputBuffer = "";

void setup() {
    Serial.begin(9600);

    gateServo.attach(SERVO_PIN);
    gateServo.write(GATE_CLOSE);
    currentAngle = GATE_CLOSE;
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
            // 뒤차 감지됨 → 타이머 리셋 (차단기 계속 올라가있음)
            gateOpenedAt = now;
            Serial.print("Rear car detected (");
            Serial.print(entryDist);
            Serial.println("cm) - keeping gate open");
        } else {
            // 뒤차 없음 → 5초 지나면 천천히 닫기 시작
            if (now - gateOpenedAt >= GATE_OPEN_TIME) {
                Serial.println("No rear car - closing gate slowly");
                closeGateWithCheck();  // 내려오면서 중간에 차 감지 시 다시 올라감
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

// 차단기 천천히 열기
void openGate(unsigned long now) {
    Serial.println("Opening gate slowly...");
    moveServoUp();
    gateIsOpen   = true;
    gateOpenedAt = now;
    Serial.println("Gate opened");
}

// 올라가기
void moveServoUp() {
    gateServo.attach(SERVO_PIN);
    for (int pos = currentAngle; pos <= GATE_OPEN; pos++) {
        gateServo.write(pos);
        delay(SERVO_SPEED);
    }
    currentAngle = GATE_OPEN;
}

// 내려오면서 차 감지 시 다시 올라가기 (핵심!)
void closeGateWithCheck() {
    gateServo.attach(SERVO_PIN);

    for (int pos = currentAngle; pos >= GATE_CLOSE; pos--) {
        gateServo.write(pos);
        currentAngle = pos;
        delay(SERVO_SPEED);

        // 내려오는 도중 초음파 체크
        int entryDist = getDistance(ENTRY_TRIG, ENTRY_ECHO);
        bool carDetected = (entryDist > 0 && entryDist < ENTRY_DETECT);

        if (carDetected) {
            // 차 감지됨 → 즉시 멈추고 다시 올라가기
            Serial.print("Car detected while closing (");
            Serial.print(entryDist);
            Serial.println("cm) - reopening gate!");

            // 현재 각도에서 다시 위로
            for (int upPos = currentAngle; upPos <= GATE_OPEN; upPos++) {
                gateServo.write(upPos);
                delay(SERVO_SPEED);
            }
            currentAngle = GATE_OPEN;
            gateIsOpen   = true;
            gateOpenedAt = millis();  // 타이머 리셋
            Serial.println("Gate reopened");
            return;  // 닫기 중단
        }
    }

    // 차 없이 완전히 닫힘
    currentAngle = GATE_CLOSE;
    delay(300);
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
