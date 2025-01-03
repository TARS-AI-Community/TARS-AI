# xTTSVOICEMODEL.MD

## Minimum Hardware Prerequisites

1. **NVIDIA GPU**: Required for optimal performance.
2. **Python Environment**: Python 3.8 or newer installed.
3. **Internet Connection**: To download the necessary model files.

---

## Cloned Voice Model Setup Guide

#### A. Set Up the XTTS API Server
Follow the instructions from [github](https://github.com/daswer123/xtts-api-server) on the PC/SERVER where the TTS processing will happen.
1. Clone REPO
    - git clone https://github.com/daswer123/xtts-api-server
    - cd xtts-api-server
2. Create virtual env
    - python -m venv venv
    - venv/scripts/activate or source venv/bin/activate
3. Install deps
    - pip install -r requirements.txt
    - pip install torch==2.1.1+cu118 torchaudio==2.1.1+cu118 --index-url https://download.pytorch.org/whl/cu118
4. Launch server to ensure it works
    - python -m xtts_api_server
5. After successfully starting the server close the server.
    
#### B. Clone the Repository
1. Open a terminal or command prompt.
2. Clone the XTTS API Server repository:
    - git clone https://github.com/daswer123/xtts-api-server.git
3. Navigate to the cloned directory:
    - cd xtts-api-server
---

#### C. Install Dependencies
1. Install the required Python packages:
    - pip install -r requirements.txt
2. Download the ALL of the Model Files from Pyrater/TARS page on Hugging Face:
    - config.json
    - vocab.json
    - model.pth
    - etc...
3. Organize the Files
    - Create a directory named tars inside the XTTS models directory. For example:
    - mkdir -p /xtts-api-server/xtts_models/tars
    - Place the downloaded files into the tars directory.
    - Place reference.wav in the speakers folder and rename it to TARS.wav
---

#### D. Launch the XTTS API Server 
1. Start the server using the following command:
    - python xtts_api_server --listen --deepspeed --lowvram --model-folder "D:/AI_Tools/xtts-api-server/xtts_models" --model-source local --version tars
    - Replace the --model-folder path if your XTTS models directory is located elsewhere.

2. Test the TARS Voice Model
    -  With the server running, use the XTTS API server's interface or provided scripts to input text.
    - Verify that the audio output emulates TARS's voice.

---

Additional Resources
    - XTTS API Server GitHub Repository
    - Local Voice Cloning Using XTTS API Server - Video Tutorial
