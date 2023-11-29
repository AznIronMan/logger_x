@echo off
NET SESSION >nul 2>&1
echo Starting Logger by GDV, LLC Installer...
echo.
if %ERRORLEVEL% neq 0 (
    echo ERROR: This script requires administrative privileges. Please run as administrator.
    echo.
    exit /b 1
)
setlocal EnableDelayedExpansion
if not exist .venv\Scripts (
    set "MIN_PYTHON_VERSION=3.11."
    set "PYTHON_VERSION_FOUND=false"
    set "PYTHON_VERSION=3.12."
    set "PYTHON_URL=https://www.python.org/ftp/python/3.12.0/python-3.12.0-amd64.exe"
    set "PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    for /f "tokens=*" %%a in ('python --version 2^>^&1') do (
        set version=%%a
        goto :check_version
    )   
    :check_version
    if defined version (
        set "extracted_version=!version:~7,5!"
        if "!extracted_version!"=="!MIN_PYTHON_VERSION!" (
            set "PYTHON_VERSION_FOUND=true"
        ) else if "!extracted_version!"=="!PYTHON_VERSION!" (
            set "PYTHON_VERSION_FOUND=true"
        )
    ) else (
        echo ERROR: Python is not installed or not found in the system path. Try manually installing Python 3.12 and try this script again.
        echo.
    )
    :FoundPython
    if exist .venv\Scripts (
        goto :End
    )
    if "!PYTHON_VERSION_FOUND!" NEQ "true" (
        echo Suitable version of Python not found.
        set /P "INSTALL_PYTHON=Do you want to download and install Python 3.12? [Y/N]: "
        set "INSTALL_PYTHON_LC=!INSTALL_PYTHON:~0,1!"
        if /I "!INSTALL_PYTHON_LC!" NEQ "y" (
            echo ERROR: Python 3.11.x or Python 3.12.x is required. Exiting.
            echo.
            exit /b 1
        )
        echo Downloading Python 3.12...
        echo.
        if not exist .installer-temp mkdir .installer-temp
        powershell -command "Invoke-WebRequest -Uri '!PYTHON_URL!' -OutFile '.installer-temp\python-3.12-installer.exe'"
        echo Installing Python 3.12...
        echo.
        .installer-temp\python-3.12-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
        if not exist "!PYTHON_PATH!" (
            echo Failed to install Python 3.12. Try manually installing Python 3.12 and try this script again.
            echo.
            exit /b 1
        )
    )
    python.exe -m venv .venv
    echo SUCCESS: Virtual environment created successfully.
    echo.
    if exist .installer-temp move .installer-temp\* .venv\python312-cache
    if exist .installer-temp rmdir .installer-temp
)
call .venv\Scripts\activate.bat
if defined VIRTUAL_ENV (
    if exist logger_help.bat echo SUCCESS: Everything looks good. You can run 'logger_help.bat' to begin logger helper.
    if exist logger_help.bat echo.
    if exist logger_help.bat goto :End
    echo Using virtual environment: %VIRTUAL_ENV%
    echo.
) else (
    echo ERROR: Failed to activate virtual environment. Try removing the .venv folder and try this script again.
    echo.
    exit /b 1
)
python.exe -m pip install --upgrade pip > nul 2>&1
pip install -r requirements.txt > nul 2>&1
pip list | findstr /C:"icecream" > nul 2>&1
if %ERRORLEVEL% == 0 (
    if exist logger_help.bat del logger_help.bat
    echo @echo off > logger_help.bat
    echo call .venv\Scripts\activate.bat >> logger_help.bat
    echo echo use 'python .\logger.py --help' to launch with args helper >> logger_help.bat
    if exist logger_help.bat (
        echo SUCCESS: Logger server installed successfully.
        echo Run 'logger_help.bat' to begin logger helper.
        echo.
    ) else (
        echo ERROR: Could not create or execute logger_help.bat.
        echo.
        exit /b 1
    )
) else (
    echo ERROR: icecream package is not installed, could not complete installation. Please try again.
    echo.
    exit /b 1
)

:End
endlocal

exit /b 0