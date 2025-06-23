# Use an official Python runtime as a parent image
FROM python:3.12-slim-bullseye

# Install ffmpeg and other dependencies
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Set environment variable for ffmpeg path (optional, but makes your code portable)
ENV FFMPEG_PATH=ffmpeg

# Expose the port FastAPI will run on
EXPOSE ${PORT:-8000}

# Command to run the app
CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]