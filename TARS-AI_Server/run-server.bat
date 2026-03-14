@echo off
setlocal EnableDelayedExpansion
title TARS-AI Server

:: ---------------------------------------------------------------------------
:: TARS-AI Companion Server — Windows installer & launcher
:: Just double-click or run from any terminal. No admin rights required.
:: ---------------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "SERVER=%SCRIPT_DIR%app-server.py"

echo.
echo  ================================================
echo   TARS-AI Companion Server
echo  ================================================
echo.

:: ---------------------------------------------------------------------------
:: Check app-server.py exists
:: ---------------------------------------------------------------------------
if not exist "%SERVER%" (
    echo  [FAIL] app-server.py not found in %SCRIPT_DIR%
    echo         Make sure run-server.bat is in the same folder as app-server.py
    goto :error
)

:: ---------------------------------------------------------------------------
:: Step 1 — Find Python 3.10+
:: ---------------------------------------------------------------------------
echo  [....] Checking Python...

set "PYTHON_CMD="
for %%C in (python python3) do (
    if not defined PYTHON_CMD (
        where %%C >nul 2>&1
        if !errorlevel! == 0 (
            for /f "tokens=2 delims= " %%V in ('%%C --version 2^>^&1') do (
                for /f "tokens=1,2 delims=." %%M in ("%%V") do (
                    if %%M == 3 (
                        if %%N GEQ 10 (
                            set "PYTHON_CMD=%%C"
                            echo  [ OK ] Found Python %%V
                        ) else (
                            echo  [ !! ] Python %%V is too old ^(need 3.10+^)
                        )
                    )
                )
            )
        )
    )
)

if not defined PYTHON_CMD (
    echo.
    echo  [FAIL] Python 3.10+ not found.
    echo.
    echo         Install it from: https://www.python.org/downloads/
    echo         Or via winget:   winget install Python.Python.3.11
    echo.
    echo         Make sure to check "Add Python to PATH" during install.
    goto :error
)

:: ---------------------------------------------------------------------------
:: Step 2 — Create venv if needed
:: ---------------------------------------------------------------------------
echo  [....] Setting up virtual environment...

if exist "%VENV_PYTHON%" (
    echo  [ OK ] Virtual environment already exists - skipping.
) else (
    echo         Creating .venv in %VENV_DIR%...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo  [FAIL] Failed to create virtual environment.
        goto :error
    )
    echo  [ OK ] Virtual environment created.
)

:: ---------------------------------------------------------------------------
:: Step 3 — Upgrade pip
:: ---------------------------------------------------------------------------
echo  [....] Upgrading pip...
"%VENV_PYTHON%" -m pip install --upgrade pip setuptools wheel
if !errorlevel! neq 0 (
    echo  [ !! ] pip upgrade failed - continuing anyway...
) else (
    echo  [ OK ] pip is up to date.
)

:: ---------------------------------------------------------------------------
:: Step 4 — Detect NVIDIA GPU
:: ---------------------------------------------------------------------------
set "HAS_GPU=0"
where nvidia-smi >nul 2>&1
if !errorlevel! == 0 (
    nvidia-smi >nul 2>&1
    if !errorlevel! == 0 (
        set "HAS_GPU=1"
    )
)

:: ---------------------------------------------------------------------------
:: Step 5 — Install PyTorch (skip if already installed)
:: ---------------------------------------------------------------------------
echo  [....] Checking PyTorch...

"%VENV_PYTHON%" -c "import torch" >nul 2>&1
if !errorlevel! == 0 (
    for /f %%V in ('"%VENV_PYTHON%" -c "import torch; print(torch.__version__)"') do (
        echo  [ OK ] PyTorch %%V already installed - skipping.
    )
) else (
    if "%HAS_GPU%"=="1" (
        echo  [....] NVIDIA GPU detected - installing PyTorch CUDA 12.4 build...
        echo         ^(This is a large download ~2.5 GB, please wait^)
        "%VENV_PIP%" install "torch>=2.6.0" "torchaudio>=2.6.0" ^
            --index-url https://download.pytorch.org/whl/cu124
    ) else (
        echo  [....] No NVIDIA GPU - installing PyTorch CPU build...
        "%VENV_PIP%" install "torch>=2.6.0" "torchaudio>=2.6.0"
    )
    if !errorlevel! neq 0 (
        echo  [FAIL] Failed to install PyTorch.
        goto :error
    )
    echo  [ OK ] PyTorch installed.
)

:: ---------------------------------------------------------------------------
:: Step 6 — Install all other dependencies (skip if already present)
:: ---------------------------------------------------------------------------
echo  [....] Checking dependencies...

"%VENV_PYTHON%" -c "import fastapi" >nul 2>&1
if !errorlevel! == 0 (
    echo  [ OK ] Dependencies already installed - skipping.
) else (
    echo  [....] Installing packages ^(this may take several minutes on first run^)...
    echo.

    "%VENV_PIP%" install ^
        "python-multipart" ^
        "fastapi>=0.104.0" ^
        "uvicorn[standard]>=0.24.0" ^
        "faster-whisper>=1.0.0" ^
        "piper-tts>=1.2.0" ^
        "transformers>=4.51.0" ^
        "accelerate>=0.27.0" ^
        "Pillow>=10.0.0" ^
        "diffusers>=0.27.0" ^
        "sentence-transformers>=2.2.0" ^
        "qrcode[pil]>=7.0" ^
        "psutil>=5.9.0"

    if !errorlevel! neq 0 (
        echo  [FAIL] Failed to install dependencies.
        goto :error
    )

    if "%HAS_GPU%"=="1" (
        echo  [....] Installing bitsandbytes ^(GPU quantization^)...
        "%VENV_PIP%" install "bitsandbytes>=0.43.0"
        if !errorlevel! neq 0 (
            echo  [ !! ] bitsandbytes install failed - continuing without it.
        )
    )

    echo  [ OK ] Dependencies installed.
)

:: Note: llama-cpp-python is installed automatically by app-server.py at
:: runtime using pre-built wheels. No compiler or Visual Studio needed.

:: ---------------------------------------------------------------------------
:: Step 7 — Launch the server
:: ---------------------------------------------------------------------------
echo.
:: Resolve LAN IP for display
for /f "tokens=2 delims=:" %%I in ('ipconfig ^| findstr /R /C:"IPv4 Address" ^| findstr /V "127.0.0.1" ^| findstr /V "172\." ^| head -1 2^>nul') do set "LAN_IP=%%I"
:: Fallback using PowerShell if the above didn't work
if not defined LAN_IP (
    for /f %%I in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '172.*' } | Select-Object -First 1).IPAddress" 2^>nul') do set "LAN_IP=%%I"
)
:: Strip leading space that ipconfig adds
if defined LAN_IP set "LAN_IP=%LAN_IP: =%"
if not defined LAN_IP set "LAN_IP=localhost"

echo  ================================================
if "%HAS_GPU%"=="1" (
    echo   GPU : NVIDIA detected
) else (
    echo   GPU : None ^(CPU mode^)
)
echo   URL : http://%LAN_IP%:5678
echo  ================================================
echo.

"%VENV_PYTHON%" "%SERVER%" %*
set EXIT_CODE=!errorlevel!

if !EXIT_CODE! neq 0 (
    echo.
    echo  [FAIL] Server exited with code !EXIT_CODE!
    goto :error
)
goto :end

:: ---------------------------------------------------------------------------
:error
echo.
pause
exit /b 1

:end
endlocal
