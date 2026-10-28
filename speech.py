
import whisper
import torch
import sounddevice as sd
import numpy as np
import tempfile
import wave
import os
import time
import re
import threading
from collections import deque

MODEL_NAME = os.environ.get("JARVIS_WHISPER_MODEL", "tiny.en")
SAMPLE_RATE = 16000
DEFAULT_RECORD_SECONDS = 5
WAKE_WINDOW_SECONDS = 4
WAKE_CHECK_SECONDS = 2
WAKE_RMS_THRESHOLD = 12
COMMAND_MAX_SECONDS = 15
VOICE_RMS_THRESHOLD = 12
TRAILING_SILENCE_SECONDS = 1.2
INPUT_BLOCK_FRAMES = 1600
ACTIVITY_BLOCK_FRAMES = int(SAMPLE_RATE * 0.25)
WAKE_PHRASE = re.compile(
    r"\b(?:(?:hey|okay|ok|hi)[\s,.:;]+)?j[ae]rv(?:is|us|s)?\b",
    re.IGNORECASE,
)

try:
    CPU_THREADS = max(1, int(os.environ.get("JARVIS_CPU_THREADS", "1")))
except ValueError:
    CPU_THREADS = 1
torch.set_num_threads(CPU_THREADS)
try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    pass


def _select_input_device():
    """Use the Windows default input, with an explicit index override."""
    configured = os.environ.get("JARVIS_MIC_DEVICE")
    if configured:
        try:
            return int(configured)
        except ValueError:
            pass

    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        if default_input is not None and 0 <= int(default_input) < len(devices):
            if devices[int(default_input)]["max_input_channels"] > 0:
                return int(default_input)

        for index, device in enumerate(devices):
            if (
                device["max_input_channels"] > 0
                and "microphone array" in device["name"].lower()
            ):
                return index
    except Exception:
        pass

    return None  # Fall back to the Windows default input device.


MIC_DEVICE = _select_input_device()

print("Loading Whisper model...")
model = whisper.load_model(MODEL_NAME)
print("JARVIS speech recognition is ready, sir.")


def _capture_command(stop_event, initial_noise_floor=30.0):
    """Capture a command and stop after speech followed by a short silence."""
    chunks = []
    started_at = time.monotonic()
    speech_started = False
    silent_frames = 0
    noise_floor = max(8.0, float(initial_noise_floor))
    complete = threading.Event()

    def capture(indata, frames, _time_info, status):
        nonlocal speech_started, silent_frames, noise_floor
        if stop_event.is_set():
            raise sd.CallbackStop
        if status:
            print(f"Microphone status: {status}")
        chunks.append(indata.copy())

        samples = indata.astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples)))
        threshold = max(VOICE_RMS_THRESHOLD, noise_floor * 1.3)
        if rms >= threshold:
            speech_started = True
            silent_frames = 0
        elif speech_started:
            silent_frames += frames
        else:
            noise_floor = 0.7 * noise_floor + 0.3 * rms

        timed_out = time.monotonic() - started_at >= COMMAND_MAX_SECONDS
        silence_done = (
            speech_started
            and silent_frames >= int(TRAILING_SILENCE_SECONDS * SAMPLE_RATE)
        )
        if timed_out or silence_done:
            complete.set()
            raise sd.CallbackStop

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=MIC_DEVICE,
        blocksize=INPUT_BLOCK_FRAMES,
        callback=capture,
    ):
        while not complete.wait(0.1) and not stop_event.is_set():
            pass

    if stop_event.is_set() or not chunks:
        return None
    return np.concatenate(chunks, axis=0)


def _transcribe(audio):
    samples = audio.reshape(-1).astype(np.float32) / 32768.0
    audio_blocks = _audio_block_levels(samples, ACTIVITY_BLOCK_FRAMES)
    if len(audio_blocks):
        speech_level = float(np.percentile(audio_blocks, 90))
        gain = min(40.0, 0.08 / max(speech_level, 0.001))
        if gain > 1.0:
            samples = np.clip(samples * gain, -1.0, 1.0)
    result = model.transcribe(
        samples,
        fp16=False,
        language="en",
        condition_on_previous_text=False,
    )
    return (result.get("text") or "").strip()


def _audio_block_levels(audio, block_frames):
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    usable_frames = len(samples) // block_frames * block_frames
    if usable_frames == 0:
        return np.empty(0, dtype=np.float32)
    blocks = samples[:usable_frames].reshape(-1, block_frames)
    return np.sqrt(np.mean(blocks * blocks, axis=1))


def get_input_device_name():
    try:
        device = MIC_DEVICE if MIC_DEVICE is not None else sd.default.device[0]
        return sd.query_devices(device)["name"]
    except Exception:
        return "Windows default microphone"


def _command_after_wake(text):
    match = WAKE_PHRASE.search(text)
    if match is None:
        return None
    return text[match.end():].strip(" \t\r\n,.:;!?")


def listen_for_wake_command(stop_event, on_wake=None, on_activity=None, on_ready=None):
    """Listen continuously for “Hey Jarvis”, then return the spoken command."""
    max_frames = WAKE_WINDOW_SECONDS * SAMPLE_RATE
    check_interval = WAKE_CHECK_SECONDS * SAMPLE_RATE
    audio_chunks = deque()
    buffered_frames = 0
    total_frames = 0
    last_check_frames = 0
    buffer_lock = threading.Lock()
    wake_command = None
    noise_floor = 8.0

    def capture(indata, frames, _time_info, status):
        nonlocal buffered_frames, total_frames
        if stop_event.is_set():
            raise sd.CallbackStop
        if status:
            print(f"Microphone status: {status}")
        chunk = indata.copy()
        with buffer_lock:
            audio_chunks.append(chunk)
            buffered_frames += frames
            total_frames += frames
            while buffered_frames > max_frames and audio_chunks:
                buffered_frames -= len(audio_chunks.popleft())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=MIC_DEVICE,
        blocksize=INPUT_BLOCK_FRAMES,
        callback=capture,
    ):
        if on_ready is not None:
            on_ready()
        while not stop_event.is_set():
            time.sleep(0.1)
            with buffer_lock:
                if buffered_frames < max_frames:
                    continue
                if total_frames - last_check_frames < check_interval:
                    continue
                last_check_frames = total_frames
                audio = np.concatenate(tuple(audio_chunks), axis=0)[-max_frames:]

            samples = audio.reshape(-1).astype(np.float32)
            block_rms = _audio_block_levels(samples, ACTIVITY_BLOCK_FRAMES)
            rms = float(np.max(block_rms)) if len(block_rms) else 0.0
            if on_activity is not None:
                on_activity(rms, "")
            if not len(block_rms):
                continue
            estimated_noise = float(np.percentile(block_rms, 25))
            noise_floor = 0.5 * noise_floor + 0.5 * estimated_noise
            threshold = max(WAKE_RMS_THRESHOLD, noise_floor * 1.25)
            voiced_blocks = int(np.count_nonzero(block_rms >= threshold))
            if voiced_blocks < 2:
                continue

            transcript = _transcribe(audio)
            with buffer_lock:
                last_check_frames = total_frames
            if stop_event.is_set():
                return None
            if on_activity is not None:
                on_activity(rms, transcript)
            wake_command = _command_after_wake(transcript)
            if wake_command is not None:
                break

    if stop_event.is_set() or wake_command is None:
        return None
    if on_wake is not None:
        on_wake()
    if wake_command:
        return wake_command

    command_audio = _capture_command(stop_event, noise_floor)
    if command_audio is None:
        return None
    transcript = _transcribe(command_audio)
    command = _command_after_wake(transcript)
    return command if command is not None else transcript.strip()


def listen():
    """Record a short sample for standalone microphone checks."""
    print(f"\nListening for {DEFAULT_RECORD_SECONDS} seconds... Speak now!")
    audio = sd.rec(
        int(DEFAULT_RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        device=MIC_DEVICE,
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

