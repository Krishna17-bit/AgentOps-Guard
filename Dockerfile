FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose ports: Streamlit (8501) and FastAPI (8000)
EXPOSE 8501
EXPOSE 8000

# Make start script executable
RUN chmod +x start_docker.sh

# Run start script to boot both uvicorn and streamlit
CMD ["./start_docker.sh"]
