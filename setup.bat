@echo off
REM ToolRouter Setup Script for Windows
REM This script helps you set up the project quickly

echo ==========================================
echo ToolRouter Setup
echo ==========================================
echo.

REM Check Python version
echo Checking Python version...
python --version
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)
echo.

REM Create virtual environment
echo Creating virtual environment...
if exist venv (
    echo Virtual environment already exists. Skipping...
) else (
    python -m venv venv
    echo Virtual environment created
)
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
echo Virtual environment activated
echo.

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1
echo pip upgraded
echo.

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
echo Dependencies installed
echo.

REM Create .env file if it doesn't exist
if exist .env (
    echo .env file already exists. Skipping...
) else (
    echo Creating .env file from template...
    copy .env.example .env
    echo .env file created
    echo.
    echo WARNING: Edit .env and add your API keys!
    echo    At minimum, add one of:
    echo    - OPENAI_API_KEY
    echo    - ANTHROPIC_API_KEY
    echo    - GOOGLE_API_KEY
)
echo.

REM Create necessary directories
echo Creating project directories...
if not exist data mkdir data
if not exist models mkdir models
if not exist logs mkdir logs
echo Directories created
echo.

REM Check if predefined tools exist
if exist data\predefined_tools.json (
    echo Predefined tools found
) else (
    echo WARNING: data\predefined_tools.json not found
    echo    The framework will try to connect to MCP servers
)
echo.

REM Summary
echo ==========================================
echo Setup Complete!
echo ==========================================
echo.
echo Next steps:
echo 1. Edit .env and add your API keys
echo 2. Run: venv\Scripts\activate.bat
echo 3. Run: python phase1_generator.py
echo.
echo For more information, see QUICKSTART.md
echo.

pause

@REM Made with Bob
