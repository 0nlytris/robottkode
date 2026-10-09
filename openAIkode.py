import asyncio
import json

import requests
from openai import AsyncOpenAI, OpenAI
from openai.helpers import LocalAudioPlayer
from Baifunctions import (recognise_person, center_person, base_get_latest_frame)

MODEL = "gpt-6-luna"
TRANSCRIBE_MODEL = "gpt-transcribe"
TTS_MODEL = "gpt-4o-mini-tts"
AUDIO_URL = "http://192.168.10.124:81/audio"
RECORD_SECONDS = 4

client = AsyncOpenAI()
audio_client = OpenAI()


#---------------------------------------------
#gets WAV audio from the ESP32 and sends it directly to OpenAI
def listen():
    print("Listening...")

    try:
        response = requests.get(AUDIO_URL, params={"seconds": RECORD_SECONDS}, timeout=RECORD_SECONDS + 5)
        response.raise_for_status()
    except requests.RequestException as error:
        print("Could not get audio from ESP32:", error)
        return None

    try:
        transcription = audio_client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=("audio.wav", response.content, "audio/wav")
        )
    except Exception as error:
        print("OpenAI transcription error:", error)
        return None

    text = transcription.text.strip()
    print("You:", text)
    return text or None


#---------------------------------------------
#uses OpenAI text-to-speech and plays it
async def speak(text):
    if not text:
        return

    print("Starting TTS")

    try:
        async with client.audio.speech.with_streaming_response.create(
            model=TTS_MODEL,
            voice="marin",
            input=text,
            instructions="Speak naturally and clearly as a nice, helpful person.",
            response_format="pcm"
        ) as response:
            await LocalAudioPlayer().play(response)

    except Exception as error:
        print("OpenAI text-to-speech error:", error)

    print("Finished TTS")


def see_people():
    """
    Look at the current camera image and return the people
    that can currently be recognised.

    Use this when the user asks who is visible, whether a
    specific person is visible, or asks something that requires
    knowing who is currently in front of the robot.
    """

    return recognise_person()


def centre_on_person(name: str):
    """
    Find a specific person using the camera and try to centre
    that person in the image.

    Args:
        name: The name of the person to find and centre on.

    Use this when the user explicitly asks the robot to find,
    look at, face, or centre itself on a specific person.
    """
    success = center_person(name)
    return {"person": name, "centred": bool(success)}

def look_at_camera():
    """
    Returns a copy of the newest frame from the camera.
    If no frame is available, returns None.
    """
    frame = base_get_latest_frame()

    if frame is None:
        return [ {
            "type": "input_text",
            "text": "No frame available"
        } ]

    return [ {
        "type": "input_image",
        "image_url": ("data:image/jpeg;base64," + frame),
        "detail": "high"  # OpenAI vision detail, separate from ESP32 sensor resolution
        } ]


available_functions = {"see_people": see_people, "centre_on_person": centre_on_person, "look_at_camera": look_at_camera}


TOOLS = [
    {
        "type": "function",
        "name": "see_people",
        "description": "Look at the current camera image and return the people that can currently be recognised.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "centre_on_person",
        "description": "Find a named person and try to centre that person in the camera image.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"],
            "additionalProperties": False
        },
        "strict": True
    },
    {
        "type": "function",
        "name": "look_at_camera",
        "description": (
            "Return the robot's latest camera frame so you can visually inspect "
            "the current scene. Use this whenever answering requires seeing objects, "
            "people, clothing, colours, text, positions, actions, what somebody is "
            "holding, or anything else visible in front of the robot."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False
        },
        "strict": True
    }
]


INSTRUCTIONS = """
You are BOE, a voice assistant controlling a small mobile robot.

The user communicates with you by speaking to the robot. Their speech is
transcribed into text, and your answers are spoken aloud.

Keep responses short, natural, and conversational. Usually answer in one
or two short sentences unless more detail is necessary.

Do not explain your internal reasoning.
Do not describe internal tool calls unless the user specifically asks.

The speech-to-text system can occasionally make small transcription errors.
Use conversational context to interpret obvious errors, but do not invent
information when the intended meaning is genuinely unclear.


CAMERA AND VISUAL PERCEPTION

You have access to the robot's current camera view through camera tools.

You cannot see the physical environment unless you have used an appropriate
camera tool for the current request.

look_at_camera() gives you the latest camera frame as an image. After calling
it, inspect the image directly and use the visible information to answer the
user.

Use look_at_camera() for questions involving visual information, including:
- what the robot can currently see,
- objects in the scene,
- what a person is holding,
- clothing,
- colours,
- visible text,
- positions of objects or people,
- actions occurring in front of the robot,
- the physical surroundings.

Never claim to see something in the current environment without first using
a relevant camera tool.


FIRST-PERSON VISUAL REFERENCES

When the user uses first-person expressions such as:
- "I"
- "me"
- "my"
- "I'm"
- "what am I holding?"
- "what colour is my shirt?"
- "can you see me?"
- "what is in front of me?"

and the question requires visual information, interpret the first-person
reference as referring to the person or people currently visible to the
robot's camera.

Do not interpret "I", "me", or "my" as referring to the robot.

If exactly one person is visible, treat that visible person as the subject
of the first-person visual question unless the conversation clearly indicates
otherwise.

If multiple people are visible and the user uses an ambiguous first-person
reference, do not arbitrarily choose one person. Inspect all relevant visible
people and answer in order from the person who appears closest to the camera
to the person who appears furthest away.

For example, if the user asks:
"What am I holding?"

and several people are visible, answer in a form such as:
"The closest person appears to be holding a phone. The person behind them
appears to be holding a bottle."

Continue from closest to furthest when more people are relevant.

Estimate closest versus furthest using visible perspective cues such as
apparent body size, face size, position, and scene depth. If the ordering is
not visually clear, say so rather than pretending to know the exact distance.

When describing what people are holding, only report objects that are
actually visible or reasonably clear in the image. If an object is obscured
or uncertain, use language such as "appears to be" or say that you cannot
clearly tell.

Do not infer a person's real-world identity merely from their appearance in
the general camera image.


PERSON RECOGNITION

see_people()

This uses the robot's face-recognition system to identify known people in the
current camera view.

Use it when identity matters, for example:
- "Who can you see?"
- "Who is in front of you?"
- "Is Astrid here?"
- "Can you see Christian?"
- "Who is standing next to me?"

Do not use see_people() merely to answer an ordinary object or scene question.

If the user asks a visual question about a NAMED person, for example:
- "What is Astrid holding?"
- "What colour is Christian's shirt?"
- "Is Astrid wearing glasses?"

identity and visual appearance are both required.

In that situation, use see_people() to determine whether and where the named
person is recognised, and use look_at_camera() to inspect the image itself.
Use both results together.

Do not identify a person by visually guessing their identity. Named-person
identity must come from the face-recognition tool.


ROBOT ORIENTATION

centre_on_person(name)

This attempts to find a named person and physically orient the robot so that
the person is centred in the camera image.

Use this when the user explicitly asks the robot to orient itself towards a
person, for example:
- "Look at Astrid."
- "Find Christian."
- "Face Astrid."
- "Turn towards Christian."
- "Centre on Astrid."

Pass only the person's name as the name argument.

Do not use centre_on_person merely because the user asks whether someone is
visible or asks what they are holding.


TOOL SELECTION

Use see_people() when the important question is WHO a person is.

Use look_at_camera() when the important question is WHAT is visually present.

Use both see_people() and look_at_camera() when the user asks a visual
question about a specifically named person.

Use centre_on_person(name) when physical robot movement towards a named person
is requested.

Examples:

"Who is there?"
-> use see_people()

"What can you see?"
-> use look_at_camera()

"What am I holding?"
-> use look_at_camera()

"What are we holding?"
-> use look_at_camera() and describe the visible people from closest to
   furthest.

"What is Astrid holding?"
-> use see_people() and look_at_camera()

"Is Astrid wearing a red shirt?"
-> use see_people() and look_at_camera()

"Turn towards Astrid."
-> use centre_on_person(name="Astrid")


TOOL BEHAVIOUR

When a tool is needed:
1. Give the user one, natural acknowledgement if appropriate.
2. Call the required tool or tools.
3. Wait for the result.
4. Answer naturally using the returned information.

Do not guess a tool result before receiving it.

Do not repeatedly call the same tool unless another observation is genuinely
necessary.

If nobody can be recognised, say that you could not currently recognise
anyone.

If a requested named person cannot be recognised, say that you could not
find that person.

If the camera frame is unavailable, say that you cannot currently see the
scene.

For normal questions that do not require visual information or robot movement,
answer directly without calling a tool.
"""


messages = []


async def ask_openai(user_text):

    messages.append({
        "role": "user",
        "content": user_text
    })

    # Allows several tool-call rounds if OpenAI needs them
    for _ in range(4):

        response = await client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            input=messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        # Save assistant messages and tool calls to history
        messages.extend(response.output)

        tool_calls = [
            item for item in response.output
            if item.type == "function_call"
        ]

        # No tool was requested -> this is the final answer
        if not tool_calls:
            answer = response.output_text
            if not answer:
                return None

            return answer.strip()


        # Run every function OpenAI requested
        for tool_call in tool_calls:

            function_name = tool_call.name
            arguments = json.loads(tool_call.arguments or "{}")
            print("function called:", function_name)
            print("arguments:", arguments)

            function = available_functions.get(function_name)

            if function is None:
                result = {"error": "unknown function called"}

            else:
                try:

                    # Blocking Python functions run in a separate thread so the asyncio event loop remains free.
                    result = await asyncio.to_thread(function, **arguments)

                except Exception as error:
                    result = {"error": str(error)}

            print("results:", result)

            # Camera image output is already a content list.
            # Normal tools return JSON-compatible data.
            if isinstance(result, list):
                tool_output = result
            else:
                tool_output = json.dumps(result)

            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": tool_output
            })

    return "I couldn't complete that request."
