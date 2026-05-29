#!/bin/bash
set -e

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║       VaultX Bank Pro — Production v2.0             ║"
echo "║       SIM Swap Detection · ML · JWT · Rate Limiting ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

cd "$(dirname "$0")/backend"

# 1. Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python3 not found. Install: brew install python3"
  exit 1
fi

# 2. Virtual environment
if [ ! -d "venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate

# 3. Install deps
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

# 4. Copy .env if not exists
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "⚙️  Created .env from template"
fi

# 5. Train ML model if not exists
if [ ! -f "ml/fraud_model.pkl" ]; then
  echo ""
  echo "🤖 Training ML fraud detection model..."
  python3 ml/train_model.py
fi

echo ""
echo "✅ Everything ready!"
echo ""
echo "   🏦  Bank App    →  http://localhost:8000"
echo "   📝  Register    →  http://localhost:8000/register"
echo "   🛡️   Admin       →  http://localhost:8000/admin"
echo "   📖  API Docs    →  http://localhost:8000/api/docs"
echo ""
echo "   Press Ctrl+C to stop."
echo ""

python3 main.py
