import logging
import base64
import os
import json
import asyncio
import struct
import socket

logger = logging.getLogger(__name__)

# Service name in docker-compose.voice.yml is 'piper'
# Ensure this matches the network alias in docker-compose
PIPER_HOST = os.getenv("PIPER_HOST", "piper")
PIPER_PORT = int(os.getenv("PIPER_PORT", "10200"))

async def generate_tts(text: str) -> str:
    """
    Generates TTS audio from text using Piper via Wyoming protocol (TCP).
    Returns base64 encoded WAV string.
    """
    try:
        reader, writer = await asyncio.open_connection(PIPER_HOST, PIPER_PORT)
        
        # Wyoming protocol: Send event as JSON line
        request = {
            "type": "synthesize",
            "data": {
                "text": text
            }
        }
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()

        # Read response events
        audio_data = bytearray()
        sample_rate = 22050 # Default fallback
        
        while True:
            # Read line (JSON event)
            line = await reader.readline()
            if not line:
                break
                
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            event_type = event.get('type')
            data = event.get('data', {})
            payload_length = data.get('payload_length', 0)
            
            # If payload exists, read it immediately
            if payload_length > 0:
                payload = await reader.readexactly(payload_length)
                if event_type == 'audio-chunk':
                    audio_data.extend(payload)
                    if 'rate' in data:
                        sample_rate = data['rate']
            
            if event_type == 'run-pipeline':
                # Initial pipeline info, ignore
                pass
            elif event_type == 'audio-stop':
                break

        writer.close()
        await writer.wait_closed()
        
        if not audio_data:
            return None
            
        return create_wav(audio_data, sample_rate)

    except Exception as e:
        logger.error(f"Failed to generate TTS via Wyoming: {e}")
        return None

def create_wav(pcm_data: bytes, sample_rate: int = 22050) -> str:
    """
    Wraps raw 16-bit mono PCM data in a WAV header and returns base64 string.
    """
    num_channels = 1
    sample_width = 2 # 16-bit
    byte_rate = sample_rate * num_channels * sample_width
    block_align = num_channels * sample_width
    
    # WAV Header
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + len(pcm_data),
        b'WAVE',
        b'fmt ',
        16, 
        1, 
        num_channels, 
        sample_rate, 
        byte_rate, 
        block_align, 
        sample_width * 8, 
        b'data', 
        len(pcm_data)
    )
    
    return base64.b64encode(header + pcm_data).decode('utf-8')
