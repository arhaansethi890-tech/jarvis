
import whisper
import sounddevice as sd
import numpy as np
import tempfile
import wave
import os
import time

MODEL_NAME = "small"
SAMPLE_RATE = 16000
DEFAULT_RECORD_SECONDS = 5
MAX_RECORD_SECONDS = 60
MIC_DEVICE = None  # Use the Windows default input device.

print("Loading Whisper model...")
model = whisper.load_model(MODEL_NAME)
print("JARVIS speech recognition is ready, sir.")


def listen(stop_event=None):
    """Record speech until the caller stops it, with a 60-second safety cap.

    Standalone use keeps the old five-second sample. The GUI passes an event
    so the user can start and stop each recording with the microphone button.
    """
    if stop_event is None:
        print(f"\nListening for {DEFAULT_RECORD_SECONDS} seconds... Speak now!")
    else:
        print("\nListening... press STOP when you're finished.")

    chunks = []
    started_at = time.monotonic()

    def capture(indata, _frames, _time_info, status):
        if status:
            print(f"Microphone status: {status}")
        chunks.append(indata.copy())
        if time.monotonic() - started_at >= MAX_RECORD_SECONDS:
            raise sd.CallbackStop

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=MIC_DEVICE,
        callback=capture,
    ):
        if stop_event is None:
            time.sleep(DEFAULT_RECORD_SECONDS)
        else:
            stop_event.wait(MAX_RECORD_SECONDS)

    if not chunks:
        print("No audio was captured.")
        return ""

    audio = np.concatenate(chunks, axis=0)
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

