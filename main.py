import asyncio

from Aesp32sense import camera_loop
from openAIKode import (ask_openai, listen, speak)


#speaks during long processes
async def progress_updates(done_event):

    updates = [
        (2.5, "One moment."),
        (7.0, "I'm still working on that."),
        (14.0, "This is taking a little longer.")
    ]

    loop = asyncio.get_running_loop()
    start_time = loop.time()

    for target_time, text in updates:

        wait_time = target_time - (loop.time() - start_time)

        try:
            await asyncio.wait_for(
                done_event.wait(),
                timeout=max(0, wait_time)
            )
            return

        except asyncio.TimeoutError:
            pass

        if done_event.is_set():
            return

        await speak(text)


async def voice_loop():

    while True:
        print()
        print("1. Start listening")

        try:
            user_text = await asyncio.to_thread(listen)

        except Exception as error:
            print("Speech-to-text error:")
            print(error)
            continue

        if user_text is None:
            print("No speech recognised.")
            continue

        user_text = user_text.strip()
        print("User:", user_text)

        print("2. Sending text to OpenAI")

        done_event = asyncio.Event()
        progress_task = asyncio.create_task(progress_updates(done_event))

        try:
            answer = await ask_openai(user_text)

        except Exception as error:
            print("OpenAI error:")
            print(error)
            continue

        finally:
            done_event.set()
            await progress_task

        if answer is None:
            continue

        answer = str(answer).strip()
        print("Robot:", answer)
        print("3. Starting TTS")

        await speak(answer)

        print("4. Going back to listening")


# async def deklarerer en coroutine
# await venter på at en async-operasjon skal bli ferdig
# gather kjører flere coroutines parallelt
# to_thread lar vanlig blokkerende kode kjøre i egen tråd
async def main():

    print("starting main")
    await asyncio.gather(asyncio.to_thread(camera_loop), voice_loop())


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print()
        print("Program stopped.")
