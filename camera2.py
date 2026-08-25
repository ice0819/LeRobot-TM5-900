import cv2
import time

# =========================
# Camera settings
# =========================
CAM0_INDEX = 0
CAM8_INDEX = 2 

WIDTH = 1280
HEIGHT = 720
FPS = 30

# =========================
# Open cameras
# =========================
cap0 = cv2.VideoCapture(CAM0_INDEX, cv2.CAP_V4L2)
cap8 = cv2.VideoCapture(CAM8_INDEX, cv2.CAP_V4L2)

# 設定解析度與 FPS
for cap in [cap0, cap8]:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS)

# 檢查是否成功開啟
if not cap0.isOpened():
    print(f"[ERROR] 無法開啟相機 index {CAM0_INDEX}")

if not cap8.isOpened():
    print(f"[ERROR] 無法開啟相機 index {CAM8_INDEX}")

if not cap0.isOpened() or not cap8.isOpened():
    cap0.release()
    cap8.release()
    cv2.destroyAllWindows()
    exit()

print("[INFO] Camera 0 opened")
print("[INFO] Camera 8 opened")

print("Camera 0:")
print("  width =", cap0.get(cv2.CAP_PROP_FRAME_WIDTH))
print("  height =", cap0.get(cv2.CAP_PROP_FRAME_HEIGHT))
print("  fps =", cap0.get(cv2.CAP_PROP_FPS))

print("Camera 8:")
print("  width =", cap8.get(cv2.CAP_PROP_FRAME_WIDTH))
print("  height =", cap8.get(cv2.CAP_PROP_FRAME_HEIGHT))
print("  fps =", cap8.get(cv2.CAP_PROP_FPS))

# =========================
# Main loop
# =========================
while True:
    ret0, frame0 = cap0.read()
    ret8, frame8 = cap8.read()

    if not ret0:
        print("[WARN] Camera 0 讀取失敗")
        continue

    if not ret8:
        print("[WARN] Camera 8 讀取失敗")
        continue

    # 顯示文字標籤
    cv2.putText(frame0, "Camera Index 0", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2)

    cv2.putText(frame8, "Camera Index 8", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 2)

    # 顯示兩個視窗
    cv2.imshow("Camera 0", frame0)
    cv2.imshow("Camera 8", frame8)

    # 按 q 離開
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break

# =========================
# Release
# =========================
cap0.release()
cap8.release()
cv2.destroyAllWindows()

print("[INFO] Cameras released")