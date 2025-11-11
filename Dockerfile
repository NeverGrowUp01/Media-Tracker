FROM python:3.11-slim

WORKDIR /app

# essential build deps + distutils
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-distutils \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt

# download spaCy model
RUN python -m spacy download en_core_web_sm

COPY src/ ./src/

EXPOSE 8501
CMD ["streamlit", "run", "src/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
