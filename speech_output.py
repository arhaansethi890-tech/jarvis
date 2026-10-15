
import asyncio
import os
import tempfile
import time

import edge_tts
import pygame

VOICE = "en-GB-RyanNeural"


async def generate_speech(text, filename):
    communicator = edge_tts.Communicate(
        text,
        VOICE,
        rate="+10%",
        pitch="-5Hz"
    )
    await communicator.save(filename)


def speak(text):
    filename = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False
        ) as temp:
            filename = temp.name

        asyncio.run(generate_speech(text, filename))

        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(filename)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

    except Exception as error:
        print(f"[Voice error] {error}")

    finally:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            pygame.mixer.quit()

        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass
