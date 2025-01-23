# ENVSETUP.md

## Minimum Hardware Prerequisites

1. **Raspberry Pi**: For obvious reasons.
2. **USB Microphone**: For user input.
3. **Speaker**: For TARS output.

---

## Environment Setup Guide (IN DEVELOPMENT)

### 1. Set Up the TARS-AI Repository on Raspberry Pi

#### A. Clone the Repository
1. Open a terminal on your Raspberry Pi.
2. Clone the **TARS-AI** repository:
   ```bash
   git clone https://github.com/pyrater/TARS-AI.git
   ```
3. Navigate to the cloned directory:
   ```bash
   cd TARS-AI
   ```

#### B. Install System-Level Dependencies
These dependencies are required for various operations, including Selenium-based automation, audio processing, and format handling.

1. **Update Your System**:
   Ensure your package lists and installed software are up to date:
   ```bash
   sudo apt update
   sudo apt upgrade -y
   ```

2. **Install Chromium**:
   Chromium is the browser required for Selenium-based web automation:
   ```bash
   sudo apt install -y chromium-browser
   ```

3. **Install Chromedriver for Selenium**:
   Chromedriver allows Selenium to control Chromium:
   ```bash
   sudo apt install -y chromium-chromedriver
   ```

4. **Install SoX and Format Support Libraries**:
   SoX is a command-line tool for processing audio files. 
   ```bash
   sudo apt install -y sox libsox-fmt-all
   ```

5. **Install PortAudio Development Libraries**:
   PortAudio is a cross-platform audio input/output library.
   ```bash
   sudo apt install -y portaudio19-dev
   ```

6. **Verify Installations**:
   Confirm that the installed packages are functioning:
   - Check Chromium version:
     ```bash
     chromium-browser --version
     ```
   - Check Chromedriver version:
     ```bash
     chromedriver --version
     ```
   - Check SoX version:
     ```bash
     sox --version
     ```

#### C. Set Up the Python Environment

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   ```
2. Activate the virtual environment:
   ```bash
   source venv/bin/activate
   ```
3. Install the required dependencies under `src/`:
   ```bash
   pip install -r requirements.txt
   ```

#### D. Connect Hardware

1. Connect your **microphone** to the Raspberry Pi via USB.
2. Connect your **speaker** to the Raspberry Pi using the audio output or Bluetooth.

#### E. Set the API Key in a `.env` File (Recommended for Secure Key Management)

**Create** a `.env` file at the root of your repository based on the pre-existing .env.template file to store your API keys for your LLM and TTS service.

**`.env` Template**:
   Add the following lines to your `.env` file. Replace `your-actual-api-key` with your actual API key for the desired service:
   ```env
   # LLM
   OPENAI_API_KEY="your-actual-openai-api-key"
   OOBA_API_KEY="your-actual-ooba-api-key"
   TABBY_API_KEY="your-actual-tabby-api-key"

   # TTS
   AZURE_API_KEY="your-actual-azure-api-key"
   ```
   - Set up an OpenAI API Key (very small cost) - [OpenAI API Key](https://www.youtube.com/watch?v=OB99E7Y1cMA)
   - Set up an Azure Speech API Key (FREE) - [Azure Speech API Key](https://www.youtube.com/watch?v=e4_AytZ264Q)
      - Make sure to create a Free Azure account [Free Azure Signup](https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account?icid=azurefreeaccount)
      - Follow all the steps in the video up to `Install Azure speech Python package`.

#### F. Set the config.ini Parameters 

1. **Create** a `config.ini` file in the `src/` folder based on the pre-existing config.ini.template file.

2. Locate the `[LLM]` section and update the parameters (for OpenAI):
   ```ini
   [LLM] # Large Language Model configuration (ooba/OAI or tabby)
   llm_backend = openai
   # Set this to `openai` if using OpenAI models.
   base_url = https://api.openai.com
   # The URL for the OpenAI API.
   openai_model = gpt-4o-mini
   # Specify the OpenAI model to use (e.g., gpt-4o-mini or another supported model).
   ```

3. Locate the `[TTS]` section and update the parameters:
   ```ini
   [TTS] # Text-to-Speech configuration 
   ttsoption = azure
   # TTS backend option: [azure, local, xttsv2, TARS]
   azure_region = eastus
   # Azure region for Azure TTS (e.g., eastus)
   ...
   tts_voice = en-US-Steffan:DragonHDLatestNeural
   # Name of the cloned voice to use (e.g., TARS2)
   ```
- `tts_voice`: You can find other voices available with Azure [here](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts).
   - If en-US-Steffan:DragonHDLatestNeural gives you an error, try en-US-SteffanNeural.

#### G. Run the Program
1. Navigate to the `src/` folder within the repository:
   ```bash
   cd src/
   ```
2. Start the application:
   ```bash
   python app.py
   ```
3. The program should now be running and ready to interact using your microphone and speaker.

## (OPTIONAL) Set up XTTS Server

### 1. Prepare Your PC with NVIDIA GPU
The TTS server must run on your GPU-enabled PC due to its computational requirements.

1. Ensure **Python 3.9-3.12** is installed on your PC.
2. Install **CUDA** and **cuDNN** compatible with your NVIDIA GPU - [CUDA Installation](https://www.youtube.com/watch?v=krAUwYslS8E)
3. Install **PyTorch** compatible with your CUDA and cuDNN versions - [PyTorch Installation](https://pytorch.org/get-started/locally/)

---

### 2. Set Up XTTS API Server

#### A. Install XTTS API Server
Run the following command on your GPU-enabled PC to clone the [XTTS API Server repository](https://github.com/daswer123/xtts-api-server):

```bash
git clone https://github.com/daswer123/xtts-api-server.git
```

Follow the installation guide for your operating system:
- **Windows**:
  1. Create and activate a virtual environment:
     ```bash
     python -m venv venv
     venv\Scripts\activate
     ```
  2. Install xtts-api-server:
     ```bash
     pip install xtts-api-server
     ```

For more details, refer to the official [XTTS API Server Installation Guide](https://github.com/daswer123/xtts-api-server/tree/main).

#### B. Add the TARS.wav Speaker File
1. Download the `TARS-short.wav` and `TARS-long.wav` files from the `TARS-AI` repository under `src/tts/wakewords
/VoiceClones`. These will be the different voices you can use for TARS.
2. Place it in the `speakers/` directory within the XTTS project folder. If the directory does not exist, create it.

#### C. Start the XTTS API Server
1. Open a terminal in the `xtts-api-server` project directory.
2. Activate your virtual environment if not already active:
3. Start the XTTS API Server:
   ```bash
   python -m xtts_api_server --listen --port 8020
   ```
4. Once the server is running, open a browser and navigate to:
   ```
   http://localhost:8020/docs
   ```
5. This will open the API's Swagger documentation interface, which you can use to test the server and its endpoints.

#### D. Verify the Server
1. Locate the **GET /speakers** endpoint in the API documentation.
2. Click **"Try it out"** and then **"Execute"** to test the endpoint.
3. Ensure the response includes the `TARS-Short` and `TARS-Long` speaker files, with entries similar to:
   ```json
   [
     {
       "name": "TARS-Long",
       "voice_id": "TARS-Long",
       "preview_url": "http://localhost:8020/sample/TARS-Long.wav"
     },
     {
       "name": "TARS-Short",
       "voice_id": "TARS-Short",
       "preview_url": "http://localhost:8020/sample/TARS-Short.wav"
     }
   ]
   ```
4. Locate the **POST /tts_to_audio** endpoint in the API documentation.
5. Click **"Try it out"** and input the following JSON in the **Request Body**:
   ```json
   {
       "text": "Hello, this is TARS speaking.",
       "speaker_wav": "TARS-Short",
       "language": "en"
   }
   ```
6. Click **"Execute"** to send the request.
7. Check the response for a generated audio file. You should see a download field where you can download and listen to the audio output.

# Home Assistant Integration for TARS
This documentation outlines the integration of the TARS AI Assistant with Home Assistant, enabling automated voice-activated function calls.

## Overview
The integration allows TARS to communicate with your Home Assistant setup to automatically process voice commands. It leverages Home Assistant's "Assistant" functionality to send prompts and execute corresponding actions.

## Prerequisites
1. Ensure that Home Assistant is installed and accessible on your network.
2. Have TARS set up in your environment.
3. A long-lived access token generated from Home Assistant.

## Configuration Steps
Step 1. **Update your `config.ini` file:**
   
   Ensure the Home Assistant module is enabled and configure the URL:
   ```ini
   [HOME_ASSISTANT] # HA Module
   enabled = True
   # If set to False, the Home Assistant module will be disabled.
   url = http://homeassistant.local:8123
   # http://192.168.2.5:8123
   # Url to acccess HA from (set Token in .env file!).
   ```
   Adjust the URL if your Home Assistant is accessible via a different address.

Step 2. **Add HA_TOKEN to `.env`:**
   - Log into Home Assistant.
   - Select your user profile (bottom left).
   - In the Security menu, scroll down to "Long-lived access tokens".
   - Create a new token, name it, and **copy the token**.
   - Add this token to your `.env` file as `HA_TOKEN="INSERT TOKEN HERE"`.

**Note:** Verify the token works before closing the creation dialog.
