import cv2
import serial
import requests
import time
import re
import os
from ultralytics import YOLO
import easyocr
from PIL import ImageFont, ImageDraw, Image
import numpy as np

# =============================================
# 설정
# =============================================
MODEL_PATH     = 'minicar_yolo.pt'
ARDUINO_PORT   = 'COM4'
CONF_THRESHOLD = 0.80
COOLDOWN       = 5

# =============================================
# FastAPI 서버 주소
# =============================================
SERVER_URL    = 'http://10.69.39.246:8000/api/check-plate'
ENTRY_LOG_URL = 'http://:8000/api/entry-log'

# =============================================
# 한글 폰트 설정
# =============================================
_FONT_PATH_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_FONT = None
for _fp in _FONT_PATH_CANDIDATES:
    if os.path.exists(_fp):
        _FONT = _fp
        break

def put_korean_text(frame, text, pos, font_size=18, color=(255, 255, 255)):
    if _FONT is None:
        cv2.putText(frame, text.encode('ascii', errors='replace').decode(),
                    pos, cv2.FONT_HERSHEY_SIMPLEX, font_size / 30, color, 2)
        return frame
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = ImageFont.truetype(_FONT, font_size)
    draw.text(pos, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

# =============================================
# 번호판 형식 검증
# =============================================
def validate_plate(text):
    patterns = [
        r'^\d{2}[\uAC00-\uD7A3]\d{4}$',
        r'^\d{3}[\uAC00-\uD7A3]\d{4}$',
        r'^[\uAC00-\uD7A3]{2}\d{2}[\uAC00-\uD7A3]\d{4}$',
        r'^[\uAC00-\uD7A3]{2}\d{3}[\uAC00-\uD7A3]\d{4}$',
    ]
    return any(re.match(pattern, text) for pattern in patterns)

# =============================================
# 번호판 확인 + 입차 기록 저장
# =============================================
def process_plate(plate, ser):
    # 1. FastAPI 서버에 번호판 확인 요청
    try:
        response = requests.post(
            SERVER_URL,
            json={'plate': plate},
            timeout=10
        )
        data = response.json()
        is_resident = data.get('is_resident', False)
        print(f"[서버 응답] is_resident: {is_resident}")
    except Exception as e:
        print(f"[서버 오류] 번호판 확인 실패: {e}")
        is_resident = False

    # 2. 차단기 제어
    if is_resident: 
        print(f"[{plate}] 등록 차량 → 차단기 열림")
        if ser:
            ser.write(b'O\n')
    else:
        print(f"[{plate}] 미등록 차량 → 차단기 유지")

    # 3. 입차 기록 저장
    try:
        requests.post(
            ENTRY_LOG_URL,
            json={
                'c_number':    plate,
                'is_resident': is_resident
            },
            timeout=10
        )
        print(f"[입차 기록] 저장 완료")
    except Exception as e:
        print(f"[입차 기록] 저장 실패: {e}")

    return is_resident

# =============================================
# 메인
# =============================================
def main():
    print("==================================================")
    print("입구 차단기 시스템")
    print(f"서버 주소: {SERVER_URL}")
    print("==================================================")

    # 모델 초기화
    try:
        model  = YOLO(MODEL_PATH)
        reader = easyocr.Reader(['ko', 'en'], gpu=False)
        print(f"[OK] AI 모델 준비 완료")
        print(f"[OK] 인식 클래스: {model.names}")
    except Exception as e:
        print(f"모델 초기화 실패: {e}")
        return

    # 아두이노 연결
    try:
        ser = serial.Serial(ARDUINO_PORT, 9600, timeout=1)
        time.sleep(2)
        print(f"[OK] 아두이노 연결 완료 ({ARDUINO_PORT})")
    except Exception as e:
        print(f"아두이노 연결 실패: {e}")
        print("아두이노 없이 카메라만 실행합니다.")
        ser = None

    # 카메라 연결
    cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    if not cap.isOpened():
        print("카메라 연결 실패")
        return
    print("[OK] 카메라 연결 완료")
    print("\n모니터링 시작 (종료: q키)\n")

    last_plate = ""
    last_time  = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        curr_time = time.time()

        # YOLO 탐지
        results = model(frame, verbose=False)

        if results[0].boxes is not None and len(results[0].boxes) > 0:
            boxes      = results[0].boxes.xyxy.cpu().numpy()
            confs      = results[0].boxes.conf.cpu().numpy()
            cls_ids    = results[0].boxes.cls.cpu().numpy().astype(int)
            class_names = model.names

            for box, conf, cls_id in zip(boxes, confs, cls_ids):
                if conf < CONF_THRESHOLD:
                    continue

                label = class_names[cls_id]
                x1, y1, x2, y2 = map(int, box)

                if label == 'plate':
                    roi = frame[y1:y2, x1:x2]
                    if roi.size > 0:
                        roi_up = cv2.resize(roi, None, fx=3, fy=3,
                                           interpolation=cv2.INTER_LANCZOS4)
                        res = reader.readtext(roi_up, detail=0)

                        if res:
                            print("OCR 결과:", res)

                        if res:
                            txt = "".join(res)

                            txt = "".join(filter(str.isalnum, txt))
                            print("정제 결과:", txt)
                            print("OCR 결과:", res)
                            print("합친 결과:", txt)

                            if validate_plate(txt):
                                print("번호판 형식 통과:", txt)
                                is_new   = txt != last_plate
                                cooldown = (curr_time - last_time) > COOLDOWN

                                if is_new or cooldown:
                                    process_plate(txt, ser)
                                    last_plate = txt
                                    last_time  = curr_time

                    color = (255, 165, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    frame = put_korean_text(frame,
                                          f"[plate {conf:.2f}]",
                                          (x1, y1 - 25),
                                          font_size=16, color=color)
                    
                elif label == 'car':
                    color = (50, 205, 50)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    frame = put_korean_text(frame,
                          f"[car {conf:.2f}]",
                          (x1, y1 - 25),
                          font_size=16, color=color)

                

        # 마지막 인식 번호판 표시
        if last_plate:
            frame = put_korean_text(frame,
                                   f"마지막 인식: {last_plate}",
                                   (10, 50),
                                   font_size=20, color=(0, 255, 0))

        display = cv2.resize(frame, (1280, 720))
        cv2.imshow("입구 차단기", display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    if ser:
        ser.close()

if __name__ == "__main__":
    main()