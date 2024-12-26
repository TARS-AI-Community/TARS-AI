# ENVSETUP.md

## Hardware Prerequisites

1. **PC with NVIDIA GPU**: Ensure you have a PC with an NVIDIA GPU available for running the XTTS server.

2. **Raspberry Pi**: For obvious reasons.

---

## Step-by-Step Guide (FOR WINDOWS)

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
1. Download the `TARS-short.wav` and `TARS-long.wav` files from the `GPTARS_Interstellar` repository under `Brain/TTS/wakewords
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

---

### 3. Set Up the GPTARS_Interstellar Repository on Raspberry Pi

#### A. Clone the Repository
1. Open a terminal on your Raspberry Pi.
2. Clone the **GPTARS_Interstellar** repository:
   ```bash
   git clone https://github.com/pyrater/GPTARS_Interstellar.git
   ```
3. Navigate to the cloned directory:
   ```bash
   cd GPTARS_Interstellar
   ```

#### B. Install Chromium and Chromedriver
Chromium and Chromedriver are required for Selenium-based operations in the project.

1. **Update Your System**:
   ```bash
   sudo apt update
   sudo apt upgrade -y
   ```

2. **Install Chromium**:
   ```bash
   sudo apt install -y chromium-browser
   ```

3. **Install Chromedriver for Selenium**:
   ```bash
   sudo apt install -y chromium-chromedriver
   ```

4. **Verify Installations**:

   - Check Chromium installation:
     ```bash
     chromium-browser --version
     ```
   - Check Chromedriver installation:
     ```bash
     chromedriver --version
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
3. Install the required dependencies under `Brain/`:
   ```bash
   pip install -r requirements.txt
   ```

#### D. Connect Hardware

1. Connect your **microphone** to the Raspberry Pi via USB.
2. Connect your **speaker** to the Raspberry Pi using the audio output or Bluetooth.

#### E. Set the API Key in a `.env` File (Recommended for Secure Key Management)

To securely store and use your API keys for OpenAI, Ooba, or Tabby, create and configure a `.env` file.

**Add API Keys**:
   Add the following lines to your `.env` file. Replace `your-actual-api-key` with your actual API key for the desired service:
   ```env
   OPENAI_API_KEY=your-actual-openai-api-key
   OOBA_API_KEY=your-actual-ooba-api-key
   TABBY_API_KEY=your-actual-tabby-api-key
   ```

#### F. Set the config.ini Parameters 

1. Open the `config.ini` file located in the `Brain/` folder.

2. Locate the `[TTS]` section and update the parameters:
   ```ini
   [TTS] # Text-to-Speech configuration (about 3.4GB TTS #xttsv2 or local or TARS)
   ttsurl = http://<server-ip>:8020
   # Replace <server-ip> with the IP address of the machine running the XTTS API Server (e.g., 192.168.2.20).
   charvoice = True
   # Use character-specific voice settings.
   ttsoption = xttsv2
   # Set this to `xttsv2` to use the XTTS API Server.
   ttsclone = TARS-Short
   # Set this to the desired speaker file (e.g., `TARS-Short` or `TARS-Long`).
   ```
   - The `ttsurl` should point to the IP and port of the XTTS API Server.
   - The `ttsclone` should match the desired speaker (e.g., `TARS-Short`).

3. Locate the `[LLM]` section and update the parameters (for OpenAI):
   ```ini
   [LLM] # Large Language Model configuration (ooba/OAI or tabby)
   backend = openai
   # Set this to `openai` if using OpenAI models.
   base_url = https://api.openai.com
   # The URL for the OpenAI API.
   openai_model = gpt-4o-mini
   # Specify the OpenAI model to use (e.g., gpt-4o-mini or another supported model).
   ```
   - Confirm that the `openai_model` matches the model available with your OpenAI API key.

#### G. Run the Program
1. Navigate to the `Brain/` folder within the repository:
   ```bash
   cd Brain/
   ```
2. Start the application:
   ```bash
   python app.py
   ```
3. The program should now be running and ready to interact using your microphone and speaker.