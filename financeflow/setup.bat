@echo off
REM FinanceFlow Setup Script for Windows

echo ================================
echo FinanceFlow Platform Setup
echo ================================
echo.

REM Check Python version
echo Checking Python version...
python --version || (echo Python 3.11+ required & exit /b 1)

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Copy .env file
if not exist .env (
    echo Creating .env file...
    copy .env.example .env
    echo.
    echo WARNING: Please update .env with your configuration
)

REM Create data directory
if not exist data mkdir data

echo.
echo ================================
echo Setup complete!
echo ================================
echo.
echo Next steps:
echo 1. Update .env file with your configuration
echo 2. Start Redis: redis-server.exe
echo 3. Start Ollama: ollama serve
echo 4. In new terminal, activate venv: venv\Scripts\activate.bat
echo 5. Run platform: python -m uvicorn app.main:app --reload
echo.
pause
