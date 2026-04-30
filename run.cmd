@echo off
TITLE Pit Lake Model Launcher
SETLOCAL EnableDelayedExpansion

:: Define relative paths
SET APP_DIR=%~dp0
SET PY_DIR=%APP_DIR%.python_env
SET PY_EXE=%PY_DIR%\python.exe
SET PIP_EXE=%PY_DIR%\Scripts\pip.exe
SET PANEL_EXE=%PY_DIR%\Scripts\panel.exe

:: Check if the standalone Python environment already exists
IF NOT EXIST "%PY_EXE%" (
    echo [INFO] Python environment not found. Preparing a standalone environment...
    echo [INFO] This initial setup may take a minute or two.
    
    :: Create the hidden environment directory
    mkdir "%PY_DIR%"

    :: Download the official Python 3.11 Embeddable package
    echo [INFO] Downloading Portable Python 3.11...
    curl -# -o "%PY_DIR%\python-embed.zip" "https://www.python.org/ftp/python/3.11.8/python-3.11.8-embed-amd64.zip"

    :: Extract the zip using PowerShell
    echo [INFO] Extracting files...
    powershell -Command "Expand-Archive -Path '%PY_DIR%\python-embed.zip' -DestinationPath '%PY_DIR%' -Force"
    del "%PY_DIR%\python-embed.zip"

    :: Patch the ._pth file to enable site-packages (Required for pip to work)
    echo [INFO] Configuring Python...
    powershell -Command "(Get-Content '%PY_DIR%\python311._pth') -replace '#import site', 'import site' | Set-Content '%PY_DIR%\python311._pth'"

    :: Download pip
    echo [INFO] Downloading pip installer...
    curl -# -o "%PY_DIR%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py"

    :: Install pip
    echo [INFO] Installing pip...
    "%PY_EXE%" "%PY_DIR%\get-pip.py" --no-warn-script-location

    :: Install the required Python libraries
    echo [INFO] Installing required libraries from requirements.txt...
    "%PIP_EXE%" install -r "%APP_DIR%requirements.txt" --no-warn-script-location

    echo [INFO] Setup complete!
) ELSE (
    echo [INFO] Standalone environment found. Skipping setup.
)

:: Run the Panel Application
echo [INFO] Launching Pit Lake Model Dashboard...
"%PANEL_EXE%" serve "%APP_DIR%pitlake_app.py" --show

pause