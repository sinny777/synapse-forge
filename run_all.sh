#!/bin/bash
# ToolRouter - Complete Pipeline Runner
# This script runs all three phases sequentially

set -e  # Exit on error

echo "=========================================="
echo "ToolRouter - Complete Pipeline"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Please copy .env.example to .env and fill in your API keys"
    exit 1
fi

echo "✓ Prerequisites checked"
echo ""

# Phase 1: Data Generation
echo "=========================================="
echo "Phase 1: Synthetic Data Generation"
echo "=========================================="
python main.py generate
if [ $? -ne 0 ]; then
    echo "❌ Phase 1 failed!"
    exit 1
fi
echo "✓ Phase 1 complete"
echo ""

# Phase 2: Model Training
echo "=========================================="
echo "Phase 2: Model Training & Fine-Tuning"
echo "=========================================="
python main.py train
if [ $? -ne 0 ]; then
    echo "❌ Phase 2 failed!"
    exit 1
fi
echo "✓ Phase 2 complete"
echo ""

# Phase 3: Runtime
echo "=========================================="
echo "Phase 3: Runtime Execution"
echo "=========================================="
echo "Starting interactive mode..."
echo "Type 'quit' to exit"
echo ""
python main.py run

echo ""
echo "=========================================="
echo "Pipeline Complete!"
echo "=========================================="

# Made with Bob
