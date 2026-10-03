"""
eye_tracker.py
==============
A reusable, non-blocking eye-tracking module.

This extracts the gaze-detection logic from `eye_detection.py` and wraps it
in a class that runs the webcam capture + MediaPipe processing in a
background thread. This way the pygame game loop is never blocked by the
camera feed.

Usage:
    tracker = EyeTracker()
    tracker.start()
    direction, iris_x, iris_y = tracker.get_state()
    ...
    tracker.stop()
"""

import cv2
import mediapipe as mp
from collections import deque
import threading


# -----------------------------
# MediaPipe Setup
# -----------------------------

mp_face_mesh = mp.solutions.face_mesh


# -----------------------------
# Iris and Eye Landmarks
# -----------------------------

RIGHT_IRIS = [469, 470, 471, 472]
LEFT_IRIS = [474, 475, 476, 477]

# Right eye corners
RIGHT_EYE_LEFT = 33
RIGHT_EYE_RIGHT = 133

# Left eye corners
LEFT_EYE_LEFT = 362
LEFT_EYE_RIGHT = 263


class EyeTracker:
    """Runs eye-gaze detection in a background thread.

    Attributes exposed for the game:
        direction (str): "Left", "Center", "Right" or "No Face".
        iris_x, iris_y (int): current iris center in webcam pixel coords.
    """

    def __init__(self, smoothing=5):
        self.smoothing = smoothing

        self.face_mesh = mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        self.cap = cv2.VideoCapture(0)
        self.cap.set(3, 640)
        self.cap.set(4, 480)

        self.direction_history = deque(maxlen=max(1, smoothing))
        self.direction = "No Face"
        self.iris_x = 0
        self.iris_y = 0
        self.latest_frame = None

        self._thread = None
        self._running = False
        self._lock = threading.Lock()

    # ----------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------

    def start(self):
        """Start the background capture thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the background thread and release resources."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.cap.release()
        self.face_mesh.close()

    # ----------------------------------------------------------
    # Public API (thread-safe)
    # ----------------------------------------------------------

    def get_state(self):
        """Return (direction, iris_x, iris_y) read from the latest frame."""
        with self._lock:
            return self.direction, self.iris_x, self.iris_y

    def get_direction(self):
        """Return just the current gaze direction string."""
        with self._lock:
            return self.direction

    # ----------------------------------------------------------
    # Internal processing (runs in the background thread)
    # ----------------------------------------------------------

    def _run(self):
        while self._running:
            success, frame = self.cap.read()
            if not success:
                continue

            # Mirror camera
            frame = cv2.flip(frame, 1)
            height, width, _ = frame.shape

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)

            direction = "No Face"
            iris_x, iris_y = 0, 0

            if results.multi_face_landmarks:
                face = results.multi_face_landmarks[0]
                direction, iris_x, iris_y = self._detect_gaze(face, width, height)

                # Smooth direction using a moving vote
                self.direction_history.append(direction)
                direction = max(self.direction_history, key=self.direction_history.count)

            with self._lock:
                self.direction = direction
                self.iris_x = iris_x
                self.iris_y = iris_y

        self.cap.release()

    # ----------------------------------------------------------
    # Static helpers (borrowed from eye_detection.py)
    # ----------------------------------------------------------

    @staticmethod
    def _get_iris_center(face, points, width, height):
        x_values = []
        y_values = []
        for point in points:
            x = int(face.landmark[point].x * width)
            y = int(face.landmark[point].y * height)
            x_values.append(x)
            y_values.append(y)

        center_x = sum(x_values) // len(x_values)
        center_y = sum(y_values) // len(y_values)
        return center_x, center_y

    @staticmethod
    def _detect_gaze(face, width, height):
        iris_x, iris_y = EyeTracker._get_iris_center(
            face, RIGHT_IRIS, width, height
        )

        x1 = int(face.landmark[RIGHT_EYE_LEFT].x * width)
        x2 = int(face.landmark[RIGHT_EYE_RIGHT].x * width)

        # Guarantee eye_left < eye_right regardless of mirroring
        eye_left = min(x1, x2)
        eye_right = max(x1, x2)

        eye_width = eye_right - eye_left
        if eye_width <= 0:
            return "Center", iris_x, iris_y

        ratio = (iris_x - eye_left) / eye_width

        if ratio < 0.40:
            direction = "Left"
        elif ratio > 0.60:
            direction = "Right"
        else:
            direction = "Center"

        return direction, iris_x, iris_y
