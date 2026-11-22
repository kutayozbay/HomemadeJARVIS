from speech.listener import listen
from speech.speaker import speak
from agent import process_command
import time
import msvcrt

def jarvis_startup():
    speak("Initializing JARVIS...")
    time.sleep(1)
    speak("All systems are online.")
    time.sleep(1)
    speak("Good evening sir, at your command.")

def main():
    jarvis_startup()
    wake_mode = True  # Jarvis is awake by default

    while True:
        try:
            if msvcrt.kbhit():
                # Text input override
                char = msvcrt.getwch()
                if char:
                    text = input("You (text): ")
                else:
                    continue
            else:
                text = listen()

            if not text or "sorry, i could not understand" in text.lower():
                print("Could not understand. Waiting...")
                continue

            print(f"You said: {text}")

            if wake_mode:
                if "jarvis sleep" in text.lower():
                    wake_mode = False
                    speak("Going to sleep, sir.")
                    continue

                if "exit" in text.lower() or "shut down" in text.lower():
                    speak("Shutting down. Goodbye.")
                    break

                response = process_command(text)
                print(f"JARVIS: {response}")
                speak(response)

            else:
                if "hey jarvis" in text.lower():
                    wake_mode = True
                    speak("I am back online, sir.")
                    continue
                else:
                    print("JARVIS is asleep. Say 'Hey Jarvis' to wake.")
        except KeyboardInterrupt:
            speak("Shutting down manually.")
            break


if __name__ == "__main__":
    main()
