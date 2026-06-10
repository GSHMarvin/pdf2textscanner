#!/usr/bin/env bash
set -e

echo "==> Installing system dependencies (requires sudo)..."
sudo apt-get update -qq
sudo apt-get install -y python3-pip python3-venv \
  tesseract-ocr tesseract-ocr-eng \
  libgl1

echo ""
echo "==> Creating Python virtual environment..."
python3 -m venv venv

echo ""
echo "==> Installing Python packages..."
venv/bin/pip install --upgrade pip
venv/bin/pip install -r backend/requirements.txt

echo ""
echo "==> Setup complete!"
echo ""
echo "Optional: PaddleOCR for superior CJK OCR (Chinese/Japanese/Korean):"
echo "  venv/bin/pip install paddlepaddle paddleocr    # CPU"
echo "  venv/bin/pip install paddlepaddle-gpu paddleocr # GPU"
echo "  When installed, the app automatically routes CJK pages to PaddleOCR."
echo ""
echo "Optional: Tesseract CJK language packs (fallback when PaddleOCR absent):"
echo "  sudo apt-get install tesseract-ocr-chi-tra tesseract-ocr-chi-sim"
echo "  sudo apt-get install tesseract-ocr-jpn tesseract-ocr-kor"
echo ""
echo "To start the app:"
echo "  source venv/bin/activate"
echo "  cd backend && uvicorn main:app --reload"
echo ""
echo "Then open: http://localhost:8000"
