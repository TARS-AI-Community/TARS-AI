@echo off
setlocal EnableDelayedExpansion
title TARS-AI Wake Word Trainer

:: ---------------------------------------------------------------------------
:: TARS-AI Wake Word Trainer — Windows installer & launcher
:: ---------------------------------------------------------------------------

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "TRAINER=%SCRIPT_DIR%app-train.py"

echo.
echo  ================================================
echo   TARS-AI Wake Word Trainer
echo  ================================================
echo.

:: ---------------------------------------------------------------------------
:: Check train.py exists
:: ---------------------------------------------------------------------------
if not exist "%TRAINER%" (
    echo  [FAIL] app-train.py not found in %SCRIPT_DIR%
    goto :error
)

:: ---------------------------------------------------------------------------
:: Step 1 — Find Python 3.10+
:: ---------------------------------------------------------------------------
echo  [....] Checking Python...

set "PYTHON_CMD="

:: Try py launcher first
where py >nul 2>&1
if !errorlevel! == 0 (
    for /f "tokens=2 delims= " %%V in ('py -3 --version 2^>^&1') do (
        for /f "tokens=1,2 delims=." %%M in ("%%V") do (
            if %%M == 3 if %%N GEQ 10 (
                set "PYTHON_CMD=py -3"
                echo  [ OK ] Found Python %%V
            )
        )
    )
)

:: Fallback to python/python3
if not defined PYTHON_CMD (
    for %%C in (python python3) do (
        if not defined PYTHON_CMD (
            where %%C >nul 2>&1
            if !errorlevel! == 0 (
                for /f "tokens=2 delims= " %%V in ('%%C --version 2^>^&1') do (
                    for /f "tokens=1,2 delims=." %%M in ("%%V") do (
                        if %%M == 3 if %%N GEQ 10 (
                            set "PYTHON_CMD=%%C"
                            echo  [ OK ] Found Python %%V
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
    echo         Install from: https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during install.
    goto :error
)

:: ---------------------------------------------------------------------------
:: Step 2 — Create venv if needed
:: ---------------------------------------------------------------------------
echo  [....] Setting up virtual environment...

if exist "%VENV_PYTHON%" (
    echo  [ OK ] Virtual environment exists - skipping.
) else (
    echo         Creating .venv...
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
"%VENV_PYTHON%" -m pip install --upgrade pip setuptools wheel >nul 2>&1
echo  [ OK ] pip ready.

:: ---------------------------------------------------------------------------
:: Step 4 — Detect GPU and install PyTorch
:: ---------------------------------------------------------------------------
echo  [....] Checking PyTorch...

"%VENV_PYTHON%" -c "import torch" >nul 2>&1
if !errorlevel! == 0 (
    for /f %%V in ('"%VENV_PYTHON%" -c "import torch; print(torch.__version__)"') do (
        echo  [ OK ] PyTorch %%V already installed.
    )
) else (
    set "HAS_GPU=0"
    where nvidia-smi >nul 2>&1
    if !errorlevel! == 0 (
        nvidia-smi >nul 2>&1
        if !errorlevel! == 0 set "HAS_GPU=1"
    )

    if "!HAS_GPU!"=="1" (
        echo  [....] NVIDIA GPU detected - installing PyTorch CUDA...
        echo         ^(Large download ~2.5 GB, please wait^)
        :: Try CUDA 12.8 first (newest), then 12.4, then fall back to PyPI
        set "TORCH_INSTALLED=0"
        for %%I in (cu128 cu124) do (
            if "!TORCH_INSTALLED!"=="0" (
                echo         Trying %%I index...
                "%VENV_PIP%" install torch --index-url https://download.pytorch.org/whl/%%I >nul 2>&1
                if !errorlevel! == 0 (
                    set "TORCH_INSTALLED=1"
                    echo  [ OK ] PyTorch installed ^(%%I^).
                )
            )
        )
        if "!TORCH_INSTALLED!"=="0" (
            echo         Trying default PyPI...
            "%VENV_PIP%" install torch
            if !errorlevel! neq 0 (
                echo  [FAIL] Failed to install PyTorch.
                echo         Your Python version may not be supported yet.
                echo         Try using Python 3.11 or 3.12.
                goto :error
            )
            echo  [ OK ] PyTorch installed ^(PyPI^).
        )
    ) else (
        echo  [....] No GPU detected - installing PyTorch CPU...
        "%VENV_PIP%" install torch
        if !errorlevel! neq 0 (
            echo  [FAIL] Failed to install PyTorch.
            goto :error
        )
        echo  [ OK ] PyTorch installed.
    )
)

:: ---------------------------------------------------------------------------
:: Step 5 — Install other dependencies
:: ---------------------------------------------------------------------------
echo  [....] Checking dependencies...

"%VENV_PYTHON%" -c "import edge_tts" >nul 2>&1
if !errorlevel! == 0 (
    echo  [ OK ] Dependencies already installed.
) else (
    echo  [....] Installing dependencies...
    "%VENV_PIP%" install -r "%SCRIPT_DIR%requirements.txt"
    if !errorlevel! neq 0 (
        echo  [FAIL] Failed to install dependencies.
        goto :error
    )
    echo  [ OK ] Dependencies installed.
)

:: ---------------------------------------------------------------------------
:: Step 6 — Run trainer
:: ---------------------------------------------------------------------------
echo.
echo  ================================================
echo   Starting training...
echo  ================================================
echo.

"%VENV_PYTHON%" "%TRAINER%" %*

if !errorlevel! neq 0 (
    echo.
    echo  [FAIL] Training failed.
    goto :error
)

echo.
echo  ================================================
echo   Training complete!
echo.
echo   Copy hey_tars.onnx to your TARS-AI installation:
echo     TARS-AI/src/tts/hey_tars.onnx
echo  ================================================
goto :end

:: ---------------------------------------------------------------------------
:error
echo.
pause
exit /b 1

:end
echo.
pause
endlocal
