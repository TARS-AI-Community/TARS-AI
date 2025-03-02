from picamera2 import Picamera2
import cv2
import time

# Initialize the camera
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"size": (640, 480), "format": "RGB888"})
picam2.configure(config)
picam2.start()

time.sleep(2)  # Allow the camera to warm up
print("Starting video stream at 19 FPS...")

while True:
    frame = picam2.capture_array()
    cv2.imshow("Pi Camera Stream", frame)

    if cv2.waitKey(50) & 0xFF == ord("q"):  # ~19 FPS (1000ms / 50ms = 20 FPS)
        break

cv2.destroyAllWindows()
picam2.stop()
print("Stream stopped.")
