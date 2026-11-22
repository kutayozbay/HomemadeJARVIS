import webbrowser

def execute_command(text):
    if "open youtube" in text.lower():
        webbrowser.open("https://youtube.com")
    elif "open google" in text.lower():
        webbrowser.open("https://google.com")
    # Add more commands here
