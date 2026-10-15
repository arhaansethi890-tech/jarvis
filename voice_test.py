
import asyncio
import edge_tts
import pygame
import os

VOICE = "en-GB-RyanNeural"
AUDIO_FILE = "jarvis_voice.mp3"

async def main():
    text = (
        "Good evening, sir. "
        "All systems are operational. "
        "How may I assist you today?"
    )

    communicate = edge_tts.Communicate(
        text,
        VOICE,
        rate="-10%",
        pitch="-5Hz"
    )

    await communicate.save(AUDIO_FILE)
    print("JARVIS voice generated. Playing audio...")

    pygame.mixer.init()
    pygame.mixer.music.load(AUDIO_FILE)
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)

    pygame.mixer.quit()
    print("Voice test complete, sir.")

asyncio.run(main())
