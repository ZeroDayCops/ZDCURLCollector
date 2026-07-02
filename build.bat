@echo off
echo ========================================================
echo   ZDCURLCollector — Windows .exe Packaging Tool
echo ========================================================
echo.

:: Clean old build/dist directories
echo 🧹 Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo Done.
echo.

:: Check and set up PyInstaller command
set PYINSTALLER_CMD=pyinstaller

if exist venv\Scripts\pyinstaller.exe (
    echo 📦 Virtual environment PyInstaller found.
    set PYINSTALLER_CMD=venv\Scripts\pyinstaller.exe
) else (
    echo ⚠️  Virtual environment PyInstaller not found.
    echo Checking for system-wide PyInstaller...
    where pyinstaller >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo ❌ ERROR: PyInstaller is not installed!
        echo Please double-click and run "setup.bat" first to install all requirements.
        echo.
        pause
        exit /b 1
    )
)

:: Run PyInstaller build
echo ⚙️ Running PyInstaller compiler...
%PYINSTALLER_CMD% ZDCURLCollector.spec
if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ ERROR: PyInstaller compilation failed!
    echo.
    pause
    exit /b %ERRORLEVEL%
)
echo.

:: Setup runtime directory structure
echo 📁 Setting up user-writable runtime directories in dist...
if not exist dist\ZDCURLCollector\sessions mkdir dist\ZDCURLCollector\sessions
if not exist dist\ZDCURLCollector\data mkdir dist\ZDCURLCollector\data
if not exist dist\ZDCURLCollector\output mkdir dist\ZDCURLCollector\output
if not exist dist\ZDCURLCollector\config mkdir dist\ZDCURLCollector\config
if not exist dist\ZDCURLCollector\proxy mkdir dist\ZDCURLCollector\proxy

:: Copy default template configurations
echo 📋 Copying config template files...
copy .env.example dist\ZDCURLCollector\.env >nul
copy links.txt dist\ZDCURLCollector\links.txt >nul

:: Initialize empty JSON files
echo [] > dist\ZDCURLCollector\data\sent_posts.json
echo {"profiles":[]} > dist\ZDCURLCollector\config\profiles.json

echo.
echo ========================================================
echo   🎉 BUILD COMPLETED SUCCESSFULLY!
echo ========================================================
echo   The executable directory is ready at:
echo   dist\ZDCURLCollector\
echo.
echo   NOTE: Please fill in credentials in:
echo   dist\ZDCURLCollector\.env
echo ========================================================
pause
