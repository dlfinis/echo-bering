#!/usr/bin/env python3
"""
Generate realistic test audio for Echo-Bering testing.
"""

import os
from gtts import gTTS
from pydub import AudioSegment

def create_test_audio():
    """Create test audio with Spanish content."""
    text = """
    Hola mundo. Este es un video de prueba para Echo-Bering. 
    Vamos a probar la segmentación automática de capítulos.
    Primero, necesitamos verificar que la transcripción funciona correctamente.
    Luego, probaremos la segmentación semántica en capítulos temáticos.
    Finalmente, validaremos la generación de metadata enriquecida.
    """
    
    # Create Spanish TTS
    tts = gTTS(text=text, lang='es')
    tts.save("test_speech.mp3")
    
    # Convert to WAV format (required by ffmpeg)
    audio = AudioSegment.from_mp3("test_speech.mp3")
    audio.export("test_speech.wav", format="wav")
    
    # Clean up
    os.remove("test_speech.mp3")
    
    print("✅ Test audio created: test_speech.wav")

if __name__ == "__main__":
    create_test_audio()