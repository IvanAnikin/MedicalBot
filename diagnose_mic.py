"""Quick microphone diagnostic - run with: python diagnose_mic.py"""
import sounddevice as sd
import numpy as np

print("=== Audio Device Diagnostics ===\n")
print("Default input device:", sd.default.device[0])
print("Default output device:", sd.default.device[1])
print()

devices = sd.query_devices()
print("All input devices:")
for i, d in enumerate(devices):
    if d["max_input_channels"] > 0:
        marker = " <-- DEFAULT" if i == sd.default.device[0] else ""
        print(f"  [{i}] {d['name']}  (inputs: {d['max_input_channels']}, rate: {d['default_samplerate']}){marker}")

print()
print("Attempting 2-second test recording at 16000 Hz...")
print(">>> Speak into your mic NOW <<<")
try:
    recording = sd.rec(int(2 * 16000), samplerate=16000, channels=1, dtype="float32")
    sd.wait()
    level = np.abs(recording).mean()
    peak = np.abs(recording).max()
    print(f"\n  Recording complete!")
    print(f"  Mean level: {level:.6f}")
    print(f"  Peak level: {peak:.6f}")
    if peak < 0.001:
        print("\n  ⚠️  VERY LOW / SILENT - microphone is NOT capturing audio")
        print("  Possible fixes:")
        print("    1. macOS: System Settings > Privacy & Security > Microphone")
        print("       -> enable access for Terminal / iTerm / VS Code")
        print("    2. Check that the correct input device is selected in")
        print("       System Settings > Sound > Input")
        print("    3. Try specifying a device: sd.default.device = (DEVICE_ID, None)")
    else:
        print("\n  ✅ Microphone is working and capturing audio!")
except Exception as e:
    print(f"\n  ❌ Recording FAILED: {e}")
    print("  This usually means sounddevice/portaudio can't access any input device.")
