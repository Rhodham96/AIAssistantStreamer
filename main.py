#Based on a project by Anis AYARI (Defend Intelligence)
#Don't forget to cite the original project! Thank you!
#Changes about oringinal project:
#- Work with a new model (Gemini)
#- Connect to VDcable input device to make it work on discord or everywhere you want
#- Faster than the original (25s -> 10s latency)
#- Add a new feature to detect if the user is talking or not and cut the audio automatically    
#- Need to improve the latency, it is still not good enough 

# IMPORT VARIABLE ENV
import sounddevice as sd
import pyaudio
import wave
from dotenv import load_dotenv , find_dotenv
from elevenlabs import api, voices, generate, play, stream
from elevenlabs import set_api_key
from pydub import AudioSegment
from pydub.playback import play as play_pydub
import pvporcupine
from pvrecorder import PvRecorder
import os
import random
import signal
import google.generativeai as genai


load_dotenv(find_dotenv())

# Add these debug lines
print("Checking environment variables:")
print(f"ACCES_KEY_PORCUPINE: {'*' * len(os.getenv('ACCES_KEY_PORCUPINE')) if os.getenv('ACCES_KEY_PORCUPINE') else 'Not found'}")
print(f"KEYWORD_PATH_PORCUPINE: {os.getenv('KEYWORD_PATH_PORCUPINE') or 'Not found'}")

try:
    porcupine = pvporcupine.create(
        access_key=os.getenv('ACCES_KEY_PORCUPINE'),
        keyword_paths=[os.getenv('KEYWORD_PATH_PORCUPINE')]
    )
except ValueError as e:
    print(f"Error initializing Porcupine: {e}")
    print("Please check your .env file and make sure ACCES_KEY_PORCUPINE is set correctly")
    exit(1)
except Exception as e:
    print(f"Unexpected error initializing Porcupine: {e}")
    exit(1)

sd.query_devices()
#FUNCTION WAKE_WORD

# FUNCTION REC MIC

#FUNCTION SPEECH TO TEXT (whisper)
def record_audio(filename, duration=5):
    #ADD DETECTOR SILENT TO CUT AUDIO AUTOMATICALLY
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    CHUNK = 1024

    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)

    print("Recording...")

    frames = []

    for _ in range(0, int(RATE / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)

    print("Finished recording")

    stream.stop_stream()
    stream.close()
    audio.terminate()

    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))

def transcribe_audio(filename):
    try:
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        
        with sr.AudioFile(filename) as source:
            audio = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio)
                print(f"Transcribed text: {text}")
                return text
            except sr.UnknownValueError:
                print("Google Speech Recognition could not understand audio")
                return "Je n'ai pas compris, pouvez-vous répéter?"
            except sr.RequestError as e:
                print(f"Could not request results from Google Speech Recognition service; {e}")
                return "Désolé, il y a eu une erreur avec le service de reconnaissance vocale"
    except ImportError:
        print("Please install SpeechRecognition: pip install SpeechRecognition")
        return "Error: SpeechRecognition not installed"
    except Exception as e:
        print(f"An error occurred: {e}")
        return "Une erreur s'est produite"

#FUNCTION TEXT TO SPEECH (ELEVEN LABS)
def get_generate_audio(text, name_audio):
    try:
        # Set the API key
        set_api_key(os.getenv('ELEVENLAB_API_KEY'))
        
        # Generate audio
        audio = generate(
            text=text,
            voice=os.getenv("ELEVENLAB_VOICE_ID"),
            model="eleven_multilingual_v1"
        )
        
        # Save the audio to a temporary file
        with open("temp_audio.mp3", "wb") as f:
            f.write(audio)
        
        # Play through VB-Cable
        audio_segment = AudioSegment.from_mp3("temp_audio.mp3")
        audio_segment.export("temp_audio.wav", format="wav")
        
        CHUNK = 1024
        wf = wave.open("temp_audio.wav", 'rb')
        
        p = pyaudio.PyAudio()
        
        # Debug: Print all audio devices
        print("\nAvailable audio devices:")
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            print(f"{i}: {dev['name']}")
        
        # Find VB-Cable input device index
        vb_cable_index = None
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            # Updated search terms to match your system
            if any(cable_name in device_info["name"] for cable_name in 
                  ["CABLE Input", "VB-Audio", "CABLE-A Input", "VB-CABLE", "VB-Cable"]):  # Added "VB-Cable"
                vb_cable_index = i
                print(f"\nFound VB-Cable at index {i}: {device_info['name']}")
                break
        
        if vb_cable_index is None:
            print("\nVB-Cable not found! Using default output.")
            print("Please make sure VB-Cable is properly installed.")
            print("Available devices were:", [p.get_device_info_by_index(i)["name"] for i in range(p.get_device_count())])
            vb_cable_index = p.get_default_output_device_info()["index"]
        
        stream = p.open(format=p.get_format_from_width(wf.getsampwidth()),
                       channels=wf.getnchannels(),
                       rate=wf.getframerate(),
                       output=True,
                       output_device_index=vb_cable_index)
        
        data = wf.readframes(CHUNK)
        while data:
            stream.write(data)
            data = wf.readframes(CHUNK)
        
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        # Clean up temporary files
        os.remove("temp_audio.mp3")
        os.remove("temp_audio.wav")

    except Exception as e:
        print(f"Error generating audio: {e}")
        print("Attempting to reinitialize ElevenLabs connection...")
        try:
            set_api_key(os.getenv('ELEVENLAB_API_KEY'))
        except Exception as e2:
            print(f"Failed to reinitialize: {e2}")
        return

#GET REPONSE GPT
def generate_script_gemini(text, messages_prev):
    # Configure the Gemini API
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    if len(messages_prev) == 0:
        system_prompt = """Tu t'appelles Santolingo. Tu es un professeur d'anglais pédagogue, le but de la discussion c'est de faire que l'utilisateur parle en anglais. Tu dois l'aider à améliorer son anglais. Ajoute une pointe d'humour."""  # Simplified prompt
        messages_prev = [{"role": "system", "content": system_prompt}]
        
    chat = model.start_chat(history=[])
    for msg in messages_prev:
        if msg["role"] != "system":  # Skip system message as Gemini handles it differently
            chat.send_message(msg["content"])
    
    response = chat.send_message(text)
    res = response.text
    
    messages_prev.append({"role": "user", "content": text})
    messages_prev.append({"role": "assistant", "content": res})
    
    if len(messages_prev) > 10:
        messages_prev = messages_prev[:-10]
    
    return res, messages_prev

def main(messages_prev, kind, **kwargs):
    if kind == 'vocal':
        audio_filename = "recorded_audio.wav"
        print('1/4 RECORD AUDIO')
        record_audio(audio_filename)
        print('2/4 SPEECH TO TEXT')
        transcription = transcribe_audio(audio_filename)
        print(transcription)
        print('3/4 GENERATE SCRIPT')
    if kind == 'chat':
        transcription = kwargs.get('text_chat')
        messages_prev = []
    res, messages_prev = generate_script_gemini(transcription, messages_prev)
    print('4/4 TEXT TO SPEECH')
    get_generate_audio(res, 'output_elevenlabs')
    print("4/5 READING AUDIO GENERATED")
    if kind == 'vocal':
        return messages_prev

def get_random_mp3_file(folder_path):
    # First check if the directory exists
    if not os.path.exists(folder_path):
        print(f"Directory {folder_path} does not exist!")
        return None
        
    mp3_files = [file for file in os.listdir(folder_path) if file.endswith(".mp3")]
    if not mp3_files:
        print(f"No MP3 files found in {folder_path}")
        return None
    
    random_file = random.choice(mp3_files)
    return os.path.join(folder_path, random_file)

def signal_handler(signal, frame):
    print("\nProgramme terminé.")
    exit(0)

if __name__ == "__main__":
    messages_prev = []
    print('LISTENING...')
    recorder = PvRecorder(
        frame_length=porcupine.frame_length)
    recorder.start()
    print('Listening ... (press Ctrl+C to exit)')
    
    signal.signal(signal.SIGINT, signal_handler)

    # Create directories if they don't exist
    INTRO_SOUNDS_DIR = 'intro_sounds'
    if not os.path.exists(INTRO_SOUNDS_DIR):
        os.makedirs(INTRO_SOUNDS_DIR)
        print(f"Created {INTRO_SOUNDS_DIR} directory. Please add your intro sound MP3 files there.")

    while True:
        pcm = recorder.read()
        keyword_index = porcupine.process(pcm)
        if keyword_index == 0:
            print('DETECTED !!!')
            intro_audio = get_random_mp3_file(INTRO_SOUNDS_DIR)
            if intro_audio:
                song = AudioSegment.from_file(intro_audio)
                play_pydub(song)
            else:
                print("Skipping intro sound - no audio files found")
            messages_prev = main(messages_prev, kind='vocal')

#ADD TWITCH LIVE