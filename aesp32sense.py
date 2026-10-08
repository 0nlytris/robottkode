import warnings
warnings.filterwarnings(
    "ignore",
    message=r"`estimate` is deprecated.*",
    category=FutureWarning
)

#for continuous face recognition, give newest image when another module asks,
#run face recognition for specific person when asked

import cv2
import numpy as np
import pandas as pd
import requests
import threading
import time

from insightface.app import FaceAnalysis
from sklearn.metrics.pairwise import cosine_similarity


url = "http://192.168.10.124/stream"

EMBEDDINGS_PATH = "face_embeddings.csv"
THRESHOLD = 0.4


df = pd.read_csv(EMBEDDINGS_PATH)
labels = df["name"].tolist()
embeddings = df.drop(columns=["name"]).values.astype(np.float32)

app = FaceAnalysis(name="buffalo_l")
app.prepare(ctx_id=-1, det_size=(1024, 1024))

current_frame = None
current_frame_bytes = None
current_people = []


#---------------------------------------------
#takes a frame and returns the recognised people
#bbox is used by center_person
def recognise_frame(frame):
    faces = app.get(frame)
    results = []

    for face in faces:
        test_embedding = face.embedding

        similarities = cosine_similarity([test_embedding], embeddings)[0]
        best_index = np.argmax(similarities)
        similarity = float(similarities[best_index])

        if similarity >= THRESHOLD:
            name = labels[best_index]
        else:
            name = "Unknown"

        x1, y1, x2, y2 = map(int, face.bbox)

        results.append({
            "name": name,
            "similarity": round(similarity, 3),
            "bbox": [x1, y1, x2, y2]
        })

    return results


#---------------------------------------------
#reconstructs complete JPEG images from the stream
#and saves the newest OpenCV image in current_frame
def camera_reader():
    global current_frame
    global current_frame_bytes

    try:
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()
        buffer = b""

        for chunk in response.iter_content(chunk_size=4096):

            if chunk == b"":
                continue

            buffer += chunk

            while True:
                start = buffer.find(b"\xff\xd8")
                if start == -1:
                    break

                end = buffer.find(b"\xff\xd9", start)
                if end == -1:
                    break

                jpg = buffer[start:end + 2]
                current_frame_bytes = jpg
                buffer = buffer[end + 2:]

                image_array = np.frombuffer(jpg, dtype=np.uint8)
                frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                
                current_frame = frame

    except Exception as e:
        print("Kamerafeil:")
        print(e)


#---------------------------------------------
#continuously runs face recognition on the newest frame
def recognition_loop():
    global current_people

    while True:
        frame = get_latest_frame()

        if frame is None:
            time.sleep(0.01)
            continue

        current_people = recognise_frame(frame)

        #wait before the next recognition to leave resources for Ollama
        time.sleep(0.3)


#---------------------------------------------
#returns a copy of the newest frame
def get_latest_frame():
    if current_frame is None:
        return None

    return current_frame.copy()


#returns the latest continuous recognition result
def get_current_people_data():
    return current_people.copy()

def get_latest_frame_bytes():
    if current_frame_bytes is None:
        return None

    return current_frame_bytes


#---------------------------------------------
#shows the camera image and the latest recognition result
def camera_loop():
    cv2.namedWindow("Face Recognition", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Face Recognition", 800, 600)
    
    while True:

        frame = get_latest_frame()

        if frame is None:
            continue

        people = get_current_people_data()

        for person in people:

            name = person["name"]
            similarity = person["similarity"]
            x1, y1, x2, y2 = person["bbox"]

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{name} {similarity:.3f}", (x1, max(25, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("Face Recognition", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()


camera_thread = threading.Thread(target=camera_reader, daemon=True)
camera_thread.start()

recognition_thread = threading.Thread(target=recognition_loop, daemon=True)
recognition_thread.start()


if __name__ == "__main__":
    camera_loop()
