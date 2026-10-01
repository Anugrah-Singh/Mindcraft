import os
import io
import asyncio
from pathlib import Path
import edge_tts

VOICE = "en-US-ChristopherNeural"  # Clear, articulate voice

async def text_to_speech_mp3(text: str) -> bytes:
    """
    Synthesize text into MP3 audio bytes using edge-tts.
    """
    communicate = edge_tts.Communicate(text, VOICE)
    mp3_data = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_data.write(chunk["data"])
    return mp3_data.getvalue()

def synthesize_speech(text: str) -> bytes:
    """
    Synchronous wrapper for text-to-speech synthesis.
    """
    return asyncio.run(text_to_speech_mp3(text))
