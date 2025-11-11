FROM python:3.10-slim

WORKDIR /app

# Install build tools and distutils (critical for spaCy dependencies)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-distutils \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# Copy your app code
COPY src/ ./src/

# Download spaCy model at build time
RUN python -m spacy download en_core_web_sm

EXPOSE 8501

CMD ["streamlit", "run", "src/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
