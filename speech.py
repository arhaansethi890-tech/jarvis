
import whisper
import sounddevice as sd
import numpy as np
import tempfile
import wave
import os

MODEL_NAME = "small"
SAMPLE_RATE = 16000
RECORD_SECONDS = 5

print("Loading Whisper model...")
model = whisper.load_model(MODEL_NAME)
print("JARVIS speech recognition is ready, sir.")


def listen():
    print("\nListening for 5 seconds... Speak now!")

    audio = sd.rec(
    int(RECORD_SECONDS * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16",
    device=1
    )
    sd.wait()
    print("Recording complete.")
    print("Peak level:", audio.max(), audio.min())

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp:
        audio_path = temp.name

    try:
        with wave.open(audio_path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(SAMPLE_RATE)
            wav_file.writeframes(audio.tobytes())

        print("Transcribing your speech...")

        result = model.transcribe(
            audio_path,
            fp16=False,
            language="en"
        )

        text = result["text"].strip()
        print(f"You said: {text if text else '[Nothing detected]'}")
        return text

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


if __name__ == "__main__":
    while True:
        try:
            command = listen()
            if command.lower() in ["exit", "quit", "stop listening"]:
                print("Speech recognition test complete, sir.")
                break
        except KeyboardInterrupt:
            print("\nJARVIS speech test stopped.")
            break
        except Exception as error:
            print(f"Speech recognition error: {error}")
            break
