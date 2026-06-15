#!/bin/bash
# Start FastAPI backend server in the background
echo "Starting FastAPI server on port 8000..."
uvicorn server:app --host 0.0.0.0 --port 8000 &

# Start Streamlit dashboard on port 8501
echo "Starting Streamlit dashboard on port 8501..."
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
