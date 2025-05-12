@echo off
echo Starting filename cleanup...
echo.

:: Process TORSO folder
echo Processing folder: TORSO
if exist TORSO (
    cd TORSO
    for %%f in (*.stl) do (
        set "found="
        for /f "tokens=*" %%a in ('echo %%f ^| findstr /R "_1_"') do (
            set "found=yes"
        )
        if defined found (
            echo Processing: %%f
            for /f "tokens=* delims=" %%i in ('powershell -command "$f='%%f'; $parts=$f -split '_1_'; $parts[$parts.Length-1]"') do (
                echo Renaming to: %%i
                ren "%%f" "%%i" 2>nul
                if errorlevel 1 echo Failed to rename - file may already exist
            )
        ) else (
            echo No "_1_" pattern in: %%f - skipping
        )
    )
    cd ..
) else (
    echo Folder "TORSO" not found - skipping
)
echo.

:: Process RIGHT LEG NO ARMS folder
echo Processing folder: RIGHT LEG NO ARMS
if exist "RIGHT LEG NO ARMS" (
    cd "RIGHT LEG NO ARMS"
    for %%f in (*.stl) do (
        set "found="
        for /f "tokens=*" %%a in ('echo %%f ^| findstr /R "_1_"') do (
            set "found=yes"
        )
        if defined found (
            echo Processing: %%f
            for /f "tokens=* delims=" %%i in ('powershell -command "$f='%%f'; $parts=$f -split '_1_'; $parts[$parts.Length-1]"') do (
                echo Renaming to: %%i
                ren "%%f" "%%i" 2>nul
                if errorlevel 1 echo Failed to rename - file may already exist
            )
        ) else (
            echo No "_1_" pattern in: %%f - skipping
        )
    )
    cd ..
) else (
    echo Folder "RIGHT LEG NO ARMS" not found - skipping
)
echo.

:: Process RIGHT LEG folder
echo Processing folder: RIGHT LEG
if exist "RIGHT LEG" (
    cd "RIGHT LEG"
    for %%f in (*.stl) do (
        set "found="
        for /f "tokens=*" %%a in ('echo %%f ^| findstr /R "_1_"') do (
            set "found=yes"
        )
        if defined found (
            echo Processing: %%f
            for /f "tokens=* delims=" %%i in ('powershell -command "$f='%%f'; $parts=$f -split '_1_'; $parts[$parts.Length-1]"') do (
                echo Renaming to: %%i
                ren "%%f" "%%i" 2>nul
                if errorlevel 1 echo Failed to rename - file may already exist
            )
        ) else (
            echo No "_1_" pattern in: %%f - skipping
        )
    )
    cd ..
) else (
    echo Folder "RIGHT LEG" not found - skipping
)
echo.

:: Process LEFT LEG NO ARMS folder
echo Processing folder: LEFT LEG NO ARMS
if exist "LEFT LEG NO ARMS" (
    cd "LEFT LEG NO ARMS"
    for %%f in (*.stl) do (
        set "found="
        for /f "tokens=*" %%a in ('echo %%f ^| findstr /R "_1_"') do (
            set "found=yes"
        )
        if defined found (
            echo Processing: %%f
            for /f "tokens=* delims=" %%i in ('powershell -command "$f='%%f'; $parts=$f -split '_1_'; $parts[$parts.Length-1]"') do (
                echo Renaming to: %%i
                ren "%%f" "%%i" 2>nul
                if errorlevel 1 echo Failed to rename - file may already exist
            )
        ) else (
            echo No "_1_" pattern in: %%f - skipping
        )
    )
    cd ..
) else (
    echo Folder "LEFT LEG NO ARMS" not found - skipping
)
echo.

:: Process LEFT LEG folder
echo Processing folder: LEFT LEG
if exist "LEFT LEG" (
    cd "LEFT LEG"
    for %%f in (*.stl) do (
        set "found="
        for /f "tokens=*" %%a in ('echo %%f ^| findstr /R "_1_"') do (
            set "found=yes"
        )
        if defined found (
            echo Processing: %%f
            for /f "tokens=* delims=" %%i in ('powershell -command "$f='%%f'; $parts=$f -split '_1_'; $parts[$parts.Length-1]"') do (
                echo Renaming to: %%i
                ren "%%f" "%%i" 2>nul
                if errorlevel 1 echo Failed to rename - file may already exist
            )
        ) else (
            echo No "_1_" pattern in: %%f - skipping
        )
    )
    cd ..
) else (
    echo Folder "LEFT LEG" not found - skipping
)
echo.

echo Cleanup completed.
pause