"""
GarudaOne — Microphone & Speech Recognition Quick Test
======================================================
Tests whether your microphone captures audio and converts your voice into text.
"""

import sys
import speech_recognition as sr

def test_microphone():
    print("\n" + "="*60)
    print("  GarudaOne — Microphone Audio & Speech Recognition Test")
    print("="*60 + "\n")

    r = sr.Recognizer()

    # List audio devices
    print("1. Checking available microphones...")
    mics = sr.Microphone.list_microphone_names()
    if not mics:
        print("[ERROR] No microphone detected. Please check your audio settings.")
        return

    print(f"[OK] Found {len(mics)} audio input device(s). Using default system microphone.\n")

    try:
        with sr.Microphone() as source:
            print("2. Calibrating for background room noise (1 second)...")
            r.adjust_for_ambient_noise(source, duration=1.0)
            print("[OK] Calibration complete.\n")

            print("--------------------------------------------------------")
            print("PLEASE SPEAK INTO YOUR MICROPHONE NOW:")
            print("   Say: 'Garuda, take off' or 'Move left'")
            print("--------------------------------------------------------")
            
            audio = r.listen(source, timeout=8, phrase_time_limit=5)
            print("\nProcessing speech...")

            text = r.recognize_google(audio)
            print("\n" + "-"*60)
            print(f"SUCCESS: Heard -> \"{text}\"")
            print("-" * 60 + "\n")
            print("Microphone and speech recognition are working properly.")

    except sr.WaitTimeoutError:
        print("\n[WARNING] No speech heard within 8 seconds.")
        print("Make sure your microphone is not muted and speak a bit louder.")
    except sr.UnknownValueError:
        print("\n[WARNING] Audio was recorded, but words could not be recognized.")
        print("Try speaking closer to your microphone.")
    except sr.RequestError as e:
        print(f"\n[ERROR] Speech recognition service error: {e}")
        print("(Ensure your internet connection is active for speech recognition)")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")

if __name__ == "__main__":
    test_microphone()
