import cv2
import mediapipe as mp
from collections import deque


# -----------------------------
# MediaPipe Setup
# -----------------------------

mp_face_mesh = mp.solutions.face_mesh

face_mesh = mp_face_mesh.FaceMesh(
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)


# -----------------------------
# Webcam Setup
# -----------------------------

cap = cv2.VideoCapture(0)

cap.set(3, 640)
cap.set(4, 480)



# -----------------------------
# Iris and Eye Landmarks
# -----------------------------

RIGHT_IRIS = [
    469,
    470,
    471,
    472
]


LEFT_IRIS = [
    474,
    475,
    476,
    477
]


# Right eye corners (FIXED: these must belong to the SAME eye as RIGHT_IRIS)

RIGHT_EYE_LEFT = 33
RIGHT_EYE_RIGHT = 133


# Left eye corners

LEFT_EYE_LEFT = 362
LEFT_EYE_RIGHT = 263



# -----------------------------
# Smoothing Buffer
# -----------------------------

direction_history = deque(maxlen=5)



# -----------------------------
# Function to calculate iris center
# -----------------------------

def get_iris_center(face, points, width, height):

    x_values = []
    y_values = []

    for point in points:

        x = int(face.landmark[point].x * width)
        y = int(face.landmark[point].y * height)

        x_values.append(x)
        y_values.append(y)


    center_x = sum(x_values)//len(x_values)
    center_y = sum(y_values)//len(y_values)


    return center_x, center_y



# -----------------------------
# Function to detect gaze
# -----------------------------

def detect_gaze(face, width, height):


    iris_x, iris_y = get_iris_center(
        face,
        RIGHT_IRIS,
        width,
        height
    )


    x1 = int(
        face.landmark[RIGHT_EYE_LEFT].x * width
    )


    x2 = int(
        face.landmark[RIGHT_EYE_RIGHT].x * width
    )


    # FIXED: guarantee eye_left < eye_right regardless of mirroring

    eye_left = min(x1, x2)
    eye_right = max(x1, x2)


    eye_width = eye_right - eye_left


    if eye_width <= 0:
        return "Center", iris_x, iris_y



    ratio = (
        iris_x - eye_left
    ) / eye_width



    # Sensitivity values

    if ratio < 0.40:

        direction = "Left"


    elif ratio > 0.60:

        direction = "Right"


    else:

        direction = "Center"



    return direction, iris_x, iris_y




# -----------------------------
# Main Loop
# -----------------------------

while True:


    success, frame = cap.read()


    if not success:
        break


    # Mirror camera

    frame = cv2.flip(frame,1)


    height, width, _ = frame.shape



    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )


    results = face_mesh.process(rgb)



    direction = "No Face"



    if results.multi_face_landmarks:


        face = results.multi_face_landmarks[0]


        direction, iris_x, iris_y = detect_gaze(
            face,
            width,
            height
        )



        # Draw iris center

        cv2.circle(
            frame,
            (iris_x, iris_y),
            6,
            (0,255,0),
            -1
        )



        # Smooth direction

        direction_history.append(direction)


        final_direction = max(
            set(direction_history),
            key=direction_history.count
        )


        direction = final_direction



    # Display direction

    cv2.putText(
        frame,
        "Gaze : " + direction,
        (30,50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.5,
        (0,255,0),
        3
    )
    cv2.imshow("Eye Gaze Detection", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()