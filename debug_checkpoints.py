import json
from pathlib import Path

# Buscar el checkpoint de transcribe
checkpoint_files = list(Path(".").rglob("*.checkpoint/asr/*.json"))
print("Checkpoint files found:", checkpoint_files)

for cf in checkpoint_files:
    print(f"\n=== {cf} ===")
    try:
        data = json.loads(cf.read_text())
        print("Keys:", list(data.keys()))
        print("Has 'words':", 'words' in data)
        print("Words count:", len(data.get('words', [])))
        print("Has 'transcript':", 'transcript' in data)
        if 'transcript' in data:
            transcript = data['transcript']
            print("Transcript keys:", list(transcript.keys()) if isinstance(transcript, dict) else "Not dict")
            if isinstance(transcript, dict):
                print("Transcript has 'words':", 'words' in transcript)
                print("Transcript words count:", len(transcript.get('words', [])))
    except Exception as e:
        print(f"Error reading {cf}: {e}")