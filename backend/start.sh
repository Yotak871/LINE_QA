#!/bin/bash
cd /Users/user/LINE_QA/backend
exec /Users/user/LINE_QA/backend/.venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
