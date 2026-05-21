#!/bin/bash

# FinanceFlow Setup Script for Linux/Mac

echo "================================"
echo "FinanceFlow Platform Setup"
echo "================================"
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version || { echo "Python 3.11+ required"; exit 1; }

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Copy .env file
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cp .env.example .env
    echo "⚠️  Please update .env with your configuration"
fi

# Create data directory
mkdir -p data

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env file with your configuration"
echo "2. Start Redis: redis-server"
echo "3. Start Ollama: ollama serve"
echo "4. In new terminal, activate venv: source venv/bin/activate"
echo "5. Run platform: python -m uvicorn app.main:app --reload"
echo ""
