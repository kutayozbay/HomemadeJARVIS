# agent.py
import google.generativeai as genai
from config import GEMINI_API_KEY
from commands import execute_command

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-2.5-pro-exp-03-25")

# Optional: Use persistent chat mode
chat = model.start_chat(history=[])

def process_command(user_input):
    # First check for local actions
    execute_command(user_input)

    # Then ask Gemini for response
    try:
        response = chat.send_message(user_input)
        return response.text
    except Exception as e:
        return f"Sorry, something went wrong with Gemini: {e}"
