import time
import base64

from Aesp32sense import (get_latest_frame, get_current_people_data, recognise_frame, get_latest_frame_bytes)


#---------------------------------------------
#tries to centre a named person in the image
def center_person(user_text):
    print("center_person started")

    tries = 0
    FRAMETHRESHOLD = 100

    while tries < 10:
        frame = get_latest_frame()
        if frame is None:
            print("venter på første frame")
            time.sleep(0.1)
            continue

        print(f"Forsøk {tries + 1}")

        people_in_frame = recognise_frame(frame)
        found = False
        for person in people_in_frame:
            name = person["name"]
            if name.lower() in user_text.lower():
                found = True

                x1, y1, x2, y2 = person["bbox"]
                center_x = (x1 + x2) // 2
                frame_center_x = frame.shape[1] // 2
                error = center_x - frame_center_x

                if error < -FRAMETHRESHOLD:
                    print(error)
                    print("personen er til venstre, flytt kameraet til høyre")
                    #send command to the robot to turn right

                elif error > FRAMETHRESHOLD:
                    print(error)
                    print("personen er til høyre, flytt kameraet til venstre")
                    #send command to the robot to turn left

                else:
                    print("Personen er midt i bildet")
                    print(error)

                    return True

        if not found:

            print("fant ikke personen i bildet, prøver igjen")
            #send command to rotate and continue searching

        #gives the robot time to move before checking again
        time.sleep(3)

        tries += 1

    print("kunne ikke finne personen etter 10 forsøk")

    return False


#---------------------------------------------
#function used by OpenAI
#returns names from the latest continuous recognition result
def recognise_person():
    print("facial recognition running")

    people = [person["name"] for person in get_current_people_data()]
    result = {"people": people}
    print("People found:", result)
    return result


#---------------------------------------------
#function used by OpenAI to get the latest camera frame in an acceptable format
def base_get_latest_frame():
    jpeg = get_latest_frame_bytes()

    if jpeg is None:
        print("No frame available")
        return None

    encoded_frame = base64.b64encode(jpeg).decode("ascii")

    return encoded_frame
