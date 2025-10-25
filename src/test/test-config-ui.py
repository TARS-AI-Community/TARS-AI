#!/usr/bin/env python3
"""
Configuration UI Test Server - Lightweight Flask Server
This script runs just the configuration UI for testing TARS modules on macOS/Windows/Linux
without needing the full Raspberry Pi environment.

The server imports actual TARS modules from the src/modules/ directory, allowing you to:
- Test configuration management with TARS CMS
- Test web UI functionality  
- Test module integration
- Develop and debug on your local machine

Usage:
    cd src
    python test-config-ui.py
    # Then open http://localhost:5012
"""

import os
import sys
import configparser
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS

# Set up the base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

print("=" * 70)
print("🌐 TARS Configuration UI Test Server")
print("=" * 70)
print(f"📁 Working directory: {BASE_DIR}")
print("🔧 Testing TARS modules on local machine")

# Initialize Flask app
app = Flask(__name__, 
            template_folder=os.path.join(BASE_DIR, 'www', 'templates'),
            static_folder=os.path.join(BASE_DIR, 'www', 'static'))
CORS(app)

@app.route('/')
def index():
    """Serve the main page with mock data"""
    return render_template('index.html', 
                         char_name="TARS",
                         char_greeting="Configuration UI Test Mode",
                         talkinghead_base_url="http://localhost:5012")

@app.route('/get_ip')
def get_ip():
    """Mock endpoint for IP"""
    return jsonify({"talkinghead_base_url": "http://localhost:5012"})

@app.route('/get_config', methods=['GET'])
def get_config():
    """Returns the current configuration with field options for dropdowns"""
    
    # Define field options for dropdowns and hardcoded hints
    field_options = {
        # CONTROLS Section
        'CONTROLS.__section__': {'description': 'Controller settings'},
        'CONTROLS.controller_name': {'description': 'Name of the controller used for interaction'},
        'CONTROLS.enabled': {'description': 'Enable use of controller used for interaction'},
        'CONTROLS.voicemovement': {'description': 'Enable or disable movement via voice control'},
        
        # STT Section
        'STT.__section__': {'description': 'Speech-to-Text configuration'},
        'STT.wake_word': {'description': 'Wake word for activating the system'},
        'STT.sensitivity': {'description': 'Lower threshold (e.g., 1) is lenient; higher (e.g., 10) is strict for wake word detection'},
        'STT.stt_processor': {
            'options': ['vosk', 'faster-whisper', 'silero', 'fastrtc', 'external'],
            'description': 'vosk, faster-whisper, silero, fastrtc, or external'
        },
        'STT.external_url': {'description': 'URL for the STT server (if enabled)'},
        'STT.whisper_model': {
            'options': ['tiny', 'base', 'small', 'medium', 'large'],
            'description': 'Which whisper model to use for onboard whisper transcription'
        },
        'STT.vosk_model': {'description': 'Model to use for local/onboard TTS from alphacephei.com/vosk/models'},
        'STT.use_indicators': {'description': 'Use beeps to indicate when listening'},
        'STT.vad_method': {
            'options': ['silero', 'rms'],
            'description': 'Voice activity detection method'
        },
        'STT.speechdelay': {'description': 'Tenths of seconds to wait before going to sleep (20 = 2 seconds)'},
        'STT.picovoice_keyword_path': {'description': 'Relative path to the Porcupine keyword file'},
        'STT.wake_word_processor': {
            'options': ['picovoice', 'pocketsphinx', 'fastrtc'],
            'description': 'Options: picovoice, pocketsphinx, fastrtc'
        },
        
        # CHAR Section
        'CHAR.__section__': {'description': 'Character-specific details'},
        'CHAR.character_card_path': {'description': 'Path to the JSON file describing the character'},
        'CHAR.user_name': {'description': 'Name of the user interacting with the character'},
        'CHAR.user_details': {'description': 'Additional user details for context'},
        
        # LLM Section
        'LLM.__section__': {'description': 'Large Language Model configuration (OpenAI, Tabby, Ooba, or LOCAL)'},
        'LLM.llm_backend': {
            'options': ['openai', 'tabby', 'ooba', 'deepinfra'],
            'description': 'Backend for LLM: [openai, tabby, ooba, deepinfra]'
        },
        'LLM.base_url': {'description': 'URL for the LLM backend API [OpenAI: https://api.openai.com]'},
        'LLM.openai_model': {
            'description': 'OpenAI model to use for LLM if backend = openai (e.g., gpt-4o-mini, gpt-4o, gpt-3.5-turbo, gpt-4)'
        },
        'LLM.override_encoding_model': {
            'options': ['cl100k_base', 'p50k_base', 'r50k_base', 'gpt2'],
            'description': 'Model to use for counting tokens (override if automatic isn\'t working)'
        },
        'LLM.contextsize': {'description': 'Maximum token context size for LLM'},
        'LLM.max_tokens': {'description': 'Maximum tokens generated per response'},
        'LLM.temperature': {'description': 'Controls randomness in generated responses (higher = more random)'},
        'LLM.top_p': {'description': 'Probability threshold for sampling next tokens (higher = more deterministic)'},
        'LLM.seed': {'description': 'Random seed for reproducibility (-1 means no fixed seed)'},
        'LLM.systemprompt': {'description': 'Prompt defining the LLM\'s behavior'},
        'LLM.instructionprompt': {'description': 'Instructions guiding the LLM\'s response style'},
        'LLM.functioncalling': {
            'options': ['llm', 'nb'],
            'description': 'LLM (passes to model, second API call) or NB (algo to guess, super fast)'
        },
        
        # VISION Section
        'VISION.__section__': {'description': 'Vision-related configuration (e.g., image recognition)'},
        'VISION.enabled': {'description': 'Set to false to prevent loading of blip'},
        'VISION.server_hosted': {'description': 'If True, the vision server is hosted locally'},
        'VISION.base_url': {'description': 'URL for the vision server API'},
        
        # EMOTION Section
        'EMOTION.__section__': {'description': 'Emotion detection for avatars (set to false if not using avatars emotions)'},
        'EMOTION.enabled': {'description': 'Enable or disable emotion detection'},
        'EMOTION.emotion_model': {'description': 'Hugging Face model for emotion analysis'},
        
        # TTS Section
        'TTS.__section__': {'description': 'Text-to-Speech configuration'},
        'TTS.ttsoption': {
            'options': ['espeak', 'piper', 'silero', 'alltalk', 'azure', 'elevenlabs', 'openai'],
            'description': 'Onboard: espeak, piper, silero | Self-hosted: alltalk | External: azure, elevenlabs, openai'
        },
        'TTS.azure_region': {
            'options': ['eastus', 'westus', 'westus2', 'eastus2', 'centralus'],
            'description': 'Azure region for Azure TTS (e.g., eastus)'
        },
        'TTS.ttsurl': {'description': 'URL of the TTS server (i.e., alltalk)'},
        'TTS.toggle_charvoice': {'description': 'Use character-specific voice settings'},
        'TTS.tts_voice': {'description': 'Name of the cloned voice to use (e.g., TARS2 or en-US-Steffan:DragonHDLatestNeural for azure)'},
        'TTS.voice_id': {'description': 'Voice ID of ElevenLabs (e.g., JBFqnCBsd6RMkjVDRZzb)'},
        'TTS.model_id': {
            'options': ['eleven_multilingual_v2', 'eleven_monolingual_v1', 'eleven_turbo_v2'],
            'description': 'Model ID of ElevenLabs'
        },
        'TTS.openai_voice': {
            'options': ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'],
            'description': 'OpenAI voice: alloy, echo, fable, onyx, nova, shimmer'
        },
        'TTS.voice_only': {'description': 'If True, only generate voice responses (no text)'},
        'TTS.is_talking_override': {'description': 'Debug flag to override talking state'},
        'TTS.is_talking': {'description': 'Tracks whether the system is currently speaking'},
        'TTS.global_timer_paused': {'description': 'Pauses global timers'},
        
        # STABLE_DIFFUSION Section
        'STABLE_DIFFUSION.__section__': {'description': 'Stable Diffusion Image Generation Module'},
        'STABLE_DIFFUSION.enabled': {'description': 'If set to False, the Stable Diffusion module will be disabled'},
        'STABLE_DIFFUSION.service': {
            'options': ['automatic1111', 'openai'],
            'description': 'You can pick from openai (requires paid account) and automatic1111 (requires setup)'
        },
        'STABLE_DIFFUSION.url': {'description': 'URL of the Automatic1111 Install. This is where requests to generate images are sent'},
        'STABLE_DIFFUSION.prompt_prefix': {'description': 'The prefix is used to help create a specific aesthetic for the images'},
        'STABLE_DIFFUSION.prompt_postfix': {'description': 'Used for defining the visual quality and characteristics of the generated image'},
        'STABLE_DIFFUSION.seed': {'description': 'A value of -1 means a random seed will be used each time, ensuring unique results'},
        'STABLE_DIFFUSION.sampler_name': {
            'options': ['Euler a', 'Euler', 'DPM++ 2M Karras', 'DPM++ SDE Karras', 'DDIM'],
            'description': '"Euler a" is a commonly used sampler, but other options may be available'
        },
        'STABLE_DIFFUSION.denoising_strength': {'description': 'Higher values result in less noise but may make the image less detailed'},
        'STABLE_DIFFUSION.steps': {'description': 'More steps generally produce better results but take longer to complete'},
        'STABLE_DIFFUSION.cfg_scale': {'description': 'The Classifier-Free Guidance scale. Higher values give more weight to the prompt'},
        'STABLE_DIFFUSION.width': {'description': 'The width of the generated image in pixels'},
        'STABLE_DIFFUSION.height': {'description': 'The height of the generated image in pixels'},
        'STABLE_DIFFUSION.restore_faces': {'description': 'Set to True if you want better face rendering in the generated image'},
        'STABLE_DIFFUSION.negative_prompt': {'description': 'The model will attempt to avoid creating images with these characteristics'},
        
        # CHATUI Section
        'CHATUI.__section__': {'description': 'Required true for avatars'},
        'CHATUI.enabled': {'description': 'Enable or disable the chat UI'},
        
        # UI Section
        'UI.__section__': {'description': 'User Interface settings'},
        'UI.UI_enabled': {'description': 'Enable or Disable the visuals'},
        'UI.UI_template': {'description': 'Determine which UI layout you want to use'},
        'UI.maximize_console': {'description': 'Start with the console using all the screen'},
        'UI.neural_net': {'description': 'Show the neural net animation'},
        'UI.neural_net_always_visible': {'description': 'Keep the neural net active all the time'},
        'UI.screen_width': {'description': 'Adjust based on your screen resolution'},
        'UI.screen_height': {'description': 'Adjust based on your screen resolution'},
        'UI.rotation': {
            'options': ['0', '90', '180', '270'],
            'description': 'Rotation can be 0, 90, 180, 270'
        },
        'UI.use_camera_module': {'description': 'Enable the camera'},
        'UI.show_mouse': {'description': 'Enable the software mouse'},
        'UI.background_id': {
            'options': ['0', '1', '2', '3', '4', '5'],
            'description': '0=no background, 1=background image, 2=stars, 3-5=video'
        },
        'UI.fullscreen': {'description': 'Fullscreen or within a framed window'},
        'UI.font_size': {'description': 'Normally from 9 to 20 depending on your resolution'},
        'UI.target_fps': {'description': 'UI Refresh max FPS speed'},
        
        # RAG Section
        'RAG.__section__': {'description': 'RAG (Retrieval Augmented Generation) settings'},
        'RAG.strategy': {
            'options': ['naive', 'hybrid'],
            'description': 'Options: naive (vector-only), hybrid (vector + BM25)'
        },
        'RAG.top_k': {'description': 'Number of documents to retrieve'},
        
        # HOME_ASSISTANT Section
        'HOME_ASSISTANT.__section__': {'description': 'HA Module'},
        'HOME_ASSISTANT.enabled': {'description': 'If set to False, the Home Assistant module will be disabled'},
        'HOME_ASSISTANT.url': {'description': 'URL to access HA from (set Token in .env file!)'},
        
        # DISCORD Section
        'DISCORD.__section__': {'description': 'Discord bot integration'},
        'DISCORD.enabled': {'description': 'Enable or disable Discord integration'},
        'DISCORD.channel_id': {'description': 'ID of the Discord channel for communication'},
        
        # SERVO Section
        'SERVO.__section__': {'description': 'Servo motor configuration'},
        'SERVO.voicemovement': {'description': 'Enable or disable movement via voice control'},
        'SERVO.MOVEMENT_VERSION': {
            'options': ['V1', 'V2'],
            'description': 'IMPORTANT: V2 setup works with V1 but YOU CANNOT SWITCH FROM V1 to V2 WITHOUT RECONFIGURING HARDWARE'
        },
        'SERVO.portMain': {'description': 'V1 ARM: Port Main servo position'},
        'SERVO.portForarm': {'description': 'V1 ARM: Port Forearm servo position'},
        'SERVO.portHand': {'description': 'V1 ARM: Port Hand servo position'},
        'SERVO.starMain': {'description': 'V1 ARM: Starboard Main servo position'},
        'SERVO.starForarm': {'description': 'V1 ARM: Starboard Forearm servo position'},
        'SERVO.starHand': {'description': 'V1 ARM: Starboard Hand servo position'},
        'SERVO.portMainMin': {'description': 'V2 ARM: Right arm main servo minimum position'},
        'SERVO.portMainMax': {'description': 'V2 ARM: Right arm main servo maximum position'},
        'SERVO.portForarmMin': {'description': 'V2 ARM: Right arm forearm servo minimum position'},
        'SERVO.portForarmMax': {'description': 'V2 ARM: Right arm forearm servo maximum position'},
        'SERVO.portHandMin': {'description': 'V2 ARM: Right arm hand servo minimum position'},
        'SERVO.portHandMax': {'description': 'V2 ARM: Right arm hand servo maximum position'},
        'SERVO.starMainMin': {'description': 'V2 ARM: Left arm main servo minimum position'},
        'SERVO.starMainMax': {'description': 'V2 ARM: Left arm main servo maximum position'},
        'SERVO.starForarmMin': {'description': 'V2 ARM: Left arm forearm servo minimum position'},
        'SERVO.starForarmMax': {'description': 'V2 ARM: Left arm forearm servo maximum position'},
        'SERVO.starHandMin': {'description': 'V2 ARM: Left arm hand servo minimum position'},
        'SERVO.starHandMax': {'description': 'V2 ARM: Left arm hand servo maximum position'},
        'SERVO.upHeight': {'description': 'Main servo upper limit (install servo so leg mount is centered)'},
        'SERVO.neutralHeight': {'description': 'Neutral position for centering the servo'},
        'SERVO.downHeight': {'description': 'Lower limit for the center servo (CAUTION: Setting too high may cause damage)'},
        'SERVO.forwardStarboard': {'description': 'Left leg forward position'},
        'SERVO.neutralStarboard': {'description': 'Left leg neutral position'},
        'SERVO.backStarboard': {'description': 'Left leg reverse position'},
        'SERVO.perfectStaroffset': {'description': 'Left leg fine-tuning offset'},
        'SERVO.forwardPort': {'description': 'Right leg forward position'},
        'SERVO.neutralPort': {'description': 'Right leg neutral position'},
        'SERVO.backPort': {'description': 'Right leg reverse position'},
        'SERVO.perfectPortoffset': {'description': 'Right leg fine-tuning offset'},
        
        # BATTERY Section
        'BATTERY.__section__': {'description': 'INA260 Current + Voltage + Power Sensor settings'},
        'BATTERY.battery_capacity_mAh': {'description': 'Total battery capacity in milliampere-hours (e.g., 5600 mAh for a 5.6Ah battery)'},
        'BATTERY.battery_initial_voltage': {'description': 'Full charge voltage in volts (e.g., 12.6V for a fully charged 12V battery)'},
        'BATTERY.battery_cutoff_voltage': {'description': 'Minimum safe voltage before discharge should stop (e.g., 10.5V for a 12V battery)'},
        'BATTERY.auto_shutdown': {'description': 'Auto shutdown when battery is low (not implemented yet)'}
    }
    
    try:
        config_file = os.path.join(BASE_DIR, 'config.ini')
        template_file = os.path.join(BASE_DIR, 'config.ini.template')
        
        # Use template if config.ini doesn't exist
        file_to_read = config_file if os.path.exists(config_file) else template_file
        
        if not os.path.exists(file_to_read):
            return jsonify({"error": "No configuration file found"}), 404
        
        config = configparser.RawConfigParser()
        config.optionxform = str  # Preserve case
        config.read(file_to_read)
        
        # Convert to dictionary
        config_dict = {}
        for section in config.sections():
            config_dict[section] = dict(config[section])
        
        return jsonify({
            "config": config_dict,
            "field_options": field_options
        })
    except Exception as e:
        print(f"Error reading config: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/save_config', methods=['POST'])
def save_config():
    """Saves the configuration to config.ini using TARS Configuration Management System"""
    
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400
        
        data = request.get_json()
        
        # Import the TARS CMS integration from module_config
        from modules.module_config import update_config_from_web_ui
        
        # Use TARS CMS to save configuration
        result = update_config_from_web_ui(data, create_backup=True)
        
        if result["success"]:
            print(f"✅ Configuration saved successfully using TARS CMS - {result['message']}")
            if result.get("backup_location"):
                print(f"📁 Backup created at {result['backup_location']}")
            
            return jsonify({
                "success": True, 
                "message": result["message"],
                "actions_taken": result.get("actions_taken", []),
                "backup_location": result.get("backup_location"),
                "tars_cms_enabled": True
            })
        else:
            print(f"❌ Configuration save failed - {result['message']}")
            return jsonify({
                "success": False, 
                "error": result["message"],
                "errors": result.get("errors", []),
                "tars_cms_enabled": True
            }), 500
    
    except Exception as e:
        print(f"❌ Configuration save error - {str(e)}")
        return jsonify({
            "success": False, 
            "error": str(e),
            "tars_cms_enabled": False
        }), 500

@app.route('/config_sync_status', methods=['GET'])
def config_sync_status():
    """Get configuration synchronization status using TARS CMS"""
    
    try:
        from modules.module_config import get_config_sync_status
        
        status = get_config_sync_status()
        
        return jsonify({
            "success": True,
            "sync_status": status,
            "tars_cms_enabled": True
        })
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "tars_cms_enabled": False
        }), 500

# Mock endpoints for other features (so UI doesn't throw errors)
@app.route('/process_llm', methods=['POST'])
def mock_process_llm():
    return jsonify({"message": "Chat requires full app.py to be running"})

@app.route('/robot_move', methods=['POST'])
def mock_robot_move():
    return jsonify({"message": "Motion control requires full app.py to be running"})

@app.route('/execute_action', methods=['POST'])
def mock_execute_action():
    return jsonify({"message": "Actions require full app.py to be running"})

if __name__ == '__main__':
    # Check if config files exist
    config_file = os.path.join(BASE_DIR, 'config.ini')
    template_file = os.path.join(BASE_DIR, 'config.ini.template')
    
    if not os.path.exists(config_file):
        if os.path.exists(template_file):
            print("⚠️  config.ini not found, using config.ini.template")
            print("   (Configuration changes will create config.ini)")
        else:
            print("❌ ERROR: Neither config.ini nor config.ini.template found!")
            print("   Please ensure config.ini.template exists in the src/ directory")
            sys.exit(1)
    else:
        print("✅ Found config.ini")
    
    print()
    print("🚀 Starting test server...")
    print()
    print("🔗 Access the Configuration UI at:")
    print("   http://localhost:5012")
    print("   http://127.0.0.1:5012")
    print()
    print("📝 Note:")
    print("   ✅ Configuration tab - FULLY FUNCTIONAL")
    print("   ✅ TARS CMS integration - FULLY FUNCTIONAL")
    print("   ⚠️  Chat UI tab - requires full app.py")
    print("   ⚠️  Motion Control tab - requires full app.py")
    print()
    print("🧪 This server tests TARS modules on your local machine!")
    print("Press Ctrl+C to stop the server")
    print("=" * 70)
    print()
    
    try:
        app.run(
            host='0.0.0.0',
            port=5012,
            debug=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
        print("Goodbye! 👋")
