#!/bin/bash
echo "============================================"
echo "  Options Tycoon - Starting Server"
echo "  http://localhost:8000"
echo "============================================"
echo ""
python -m uvicorn main:app --reload --port 8000
