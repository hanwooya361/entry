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
# Config
# =============================================
MODEL_PATH = 'minicar_yolo.pt'
SERVER_URL = 'http://server-address/api/check-plate'
ENTRY_LOG_URL = 'http://server-address/api/entry-log'
ARDUINO_PORT = 'COM4'
CONF_THRESHOLD = 0.80
COOLDOWN = 10

# =============================================
# Font config
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
        cv2.putText(
            frame,
            text.encode('ascii', errors='replace').decode(),
            pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_size / 30,
            color,
            2,
        )
        return frame

    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = ImageFont.truetype(_FONT, font_size)
    draw.text(pos, text, font=font, fill=(color[2], color[1], color[0]))
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


class ArduinoSignal:
    def __init__(self, serial_port):
        self.serial_port = serial_port

    def write(self, data):
        try:
            signal = b'O\n' if data == b'O' else data
            self.serial_port.write(signal)
            self.serial_port.flush()
        except Exception as e:
            print(f"Arduino signal send failed: {e}")

    def close(self):
        self.serial_port.close()


def validate_plate(text):
    patterns = [
        r'^\d{2}[\uAC00-\uD7A3]\d{4}$',
        r'^\d{3}[\uAC00-\uD7A3]\d{4}$',
        r'^[\uAC00-\uD7A3]{2}\d{2}[\uAC00-\uD7A3]\d{4}$',
        r'^[\uAC00-\uD7A3]{2}\d{3}[\uAC00-\uD7A3]\d{4}$',
    ]
    return any(re.match(pattern, text) for pattern in patterns)


def main():
    print("==================================================")
    print("Entry camera system started")
    print("==================================================")

    # Initialize AI model and OCR reader.
    try:
        model = YOLO(MODEL_PATH)
        reader = easyocr.Reader(['ko', 'en'], gpu=False)
        print("[OK] AI model ready")
        print(f"[OK] Detected classes: {model.names}")
    except Exception as e:
        print(f"Model initialization failed: {e}")
        return

    # Connect to Arduino.
    try:
        arduino = ArduinoSignal(serial.Serial(ARDUINO_PORT, 9600, timeout=1))
        time.sleep(2)
        print(f"[OK] Arduino connected ({ARDUINO_PORT})")
    except Exception as e:
        print(f"Arduino connection failed: {e}")
        print("Running camera only without Arduino.")
        arduino = None

    # Connect to camera.
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    if not cap.isOpened():
        print("Camera connection failed")
        return

    print("[OK] Camera connected")
    print("\nEntry monitoring started. Press q to quit.\n")

    last_plate = ""
    last_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        curr_time = time.time()

        # Detect objects with YOLO.
        results = model(frame, verbose=False)

        if results[0].boxes is not None and len(results[0].boxes) > 0:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            confs = results[0].boxes.conf.cpu().numpy()
            cls_ids = results[0].boxes.cls.cpu().numpy().astype(int)
            class_names = model.names

            for box, conf, cls_id in zip(boxes, confs, cls_ids):
                if conf < CONF_THRESHOLD:
                    continue

                label = class_names[cls_id]
                x1, y1, x2, y2 = map(int, box)

                # Run OCR only on plate detections.
                if label == 'plate':
                    roi = frame[y1:y2, x1:x2]
                    if roi.size > 0:
                        roi_up = cv2.resize(
                            roi,
                            None,
                            fx=3,
                            fy=3,
                            interpolation=cv2.INTER_LANCZOS4,
                        )
                        res = reader.readtext(roi_up, detail=0)

                        if res:
                            txt = "".join(filter(str.isalnum, res[0]))

                            if validate_plate(txt):
                                is_new_plate = txt != last_plate
                                cooldown_passed = (curr_time - last_time) > COOLDOWN
                                if is_new_plate or cooldown_passed:
                                    print(f"\nPlate detected: {txt} ({conf:.2f})")
                                    process_plate(txt, arduino)
                                    last_plate = txt
                                    last_time = curr_time

                    color = (255, 165, 0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    frame = put_korean_text(
                        frame,
                        f"[plate {conf:.2f}]",
                        (x1, y1 - 25),
                        font_size=16,
                        color=color,
                    )

        if last_plate:
            frame = put_korean_text(
                frame,
                f"Last plate: {last_plate}",
                (10, 50),
                font_size=20,
                color=(0, 255, 0),
            )

        display = cv2.resize(frame, (1280, 720))
        cv2.imshow("Entry Camera", display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    if arduino:
        arduino.close()


def process_plate(plate, arduino):
    """Check plate, control gate, and save entry log."""

    try:
        response = requests.post(
            SERVER_URL,
            json={'plate': plate},
            timeout=3,
        )
        data = response.json()
        is_resident = data.get('is_resident', False)
    except Exception as e:
        print(f"Server request failed: {e}")
        is_resident = False

    if is_resident:
        print("Registered vehicle - opening gate")
        if arduino:
            arduino.write(b'O')
    else:
        print("Unregistered vehicle - gate remains closed")

    try:
        requests.post(
            ENTRY_LOG_URL,
            json={
                'c_number': plate,
                'is_resident': is_resident,
            },
            timeout=3,
        )
        print("Entry log saved")
    except Exception as e:
        print(f"Entry log save failed: {e}")


if __name__ == "__main__":
    main()
