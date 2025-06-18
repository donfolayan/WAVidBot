# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install ffmpeg and other dependencies
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Set environment variable for ffmpeg path (optional, but makes your code portable)
ENV FFMPEG_PATH=ffmpeg

# Expose the port FastAPI will run on
EXPOSE ${PORT:-8000}

# Command to run the app
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}