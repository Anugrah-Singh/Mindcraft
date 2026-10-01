import os
import json
from typing import Dict, Any, Optional
from google import genai
from google.genai import types
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)
load_dotenv() # Fallback to cwd if any

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Modern Google Gemini Models (Free tier / lowest cost)
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = "gemini-3.8-flash"

def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment or companion/.env file.")
    return genai.Client(api_key=api_key)

SYSTEM_PROMPT = """
You are Mindcraft AI, an ambient intelligent companion operating on an ESP32 wearable/desk device.
Your job is to listen to user speech and classify the intent into one of four actions:

1. "TASK": The user wants to create a to-do item or task.
   Extract:
   - "title": Clean concise task title (e.g., "Submit quarterly tax report")
   - "priority": "HIGH", "MEDIUM", or "LOW" based on urgency mentioned or inferred context.
   - "spoken_response": Short verbal confirmation (e.g., "Added high priority task: Submit quarterly tax report.")
   - "oled_text": Max 20 chars display summary (e.g., "Task Added: Tax report")

2. "NOTE": The user is capturing an idea, thought, memo, or voice note.
   Extract:
   - "title": Short title (e.g., "Podcast Idea on Robotics")
   - "content": Full captured note text
   - "spoken_response": Short verbal confirmation (e.g., "Note saved: Podcast Idea.")
   - "oled_text": Max 20 chars (e.g., "Note Saved!")

3. "HABIT": The user completed a daily habit or routine (e.g. gym, workout, reading, meditation, water).
   Extract:
   - "habit_name": Normalized name (e.g., "Gym", "Workout", "Water", "Read")
   - "spoken_response": Enthusiastic short confirmation (e.g., "Awesome! Gym streak logged.")
   - "oled_text": Max 20 chars (e.g., "Gym Streak +1!")

4. "CONVERSATION": General question, query, math, advice, banter, or conversational AI request.
   Extract:
   - "spoken_response": Natural, clear, concise conversational reply (keep under 25-35 words suitable for text-to-speech speaker playback).
   - "oled_text": Max 24 chars summary for OLED screen display.

Always return ONLY valid JSON matching this schema:
{
  "action": "TASK" | "NOTE" | "HABIT" | "CONVERSATION",
  "title": string or null,
  "content": string or null,
  "priority": "HIGH" | "MEDIUM" | "LOW" | null,
  "habit_name": string or null,
  "spoken_response": string,
  "oled_text": string
}
"""

def process_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> Dict[str, Any]:
    """
    Directly passes raw audio recorded from ESP32 to Gemini multimodal API.
    """
    client = get_client()
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)
    
    for selected_model in [MODEL_NAME, FALLBACK_MODEL]:
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=[
                    SYSTEM_PROMPT,
                    audio_part,
                    "Classify and respond to this audio clip according to the instructions."
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[Gemini] Warning with model {selected_model}: {e}")
            continue

    return {
        "action": "CONVERSATION",
        "spoken_response": "I heard you, but could not parse the response.",
        "oled_text": "Parse Error"
    }

def process_text_prompt(prompt_text: str) -> Dict[str, Any]:
    """
    Processes typed or transcribed text prompts.
    """
    client = get_client()
    for selected_model in [MODEL_NAME, FALLBACK_MODEL]:
        try:
            response = client.models.generate_content(
                model=selected_model,
                contents=[
                    SYSTEM_PROMPT,
                    f"User input: {prompt_text}"
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[Gemini] Warning with model {selected_model}: {e}")
            continue

    return {
        "action": "CONVERSATION",
        "spoken_response": "Sorry, I could not process that request.",
        "oled_text": "Error"
    }
