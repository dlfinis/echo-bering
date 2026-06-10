import mlx_whisper

# Test with small audio file
result = mlx_whisper.transcribe(
    'sources/test_1m.mp4',
    word_timestamps=True,
    verbose=False
)

print("Keys in result:", list(result.keys()))
print("Has 'words':", 'words' in result)
if 'words' in result:
    print("Words count:", len(result['words']))
    if result['words']:
        print("First word:", result['words'][0])
else:
    print("No 'words' key found")

print("Has 'segments':", 'segments' in result)
if 'segments' in result:
    print("Segments count:", len(result['segments']))
    if result['segments']:
        print("First segment keys:", list(result['segments'][0].keys()))
        if 'words' in result['segments'][0]:
            print("Words in first segment:", len(result['segments'][0]['words']))