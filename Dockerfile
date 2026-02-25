# Use an official Python runtime as a parent image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI (needed for some Copilot features)
RUN type -p curl >/dev/null || (apt-get update && apt-get install curl -y)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install gh -y

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY pyproject.toml .
COPY requirements.txt .
COPY src/ ./src/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir . \
    && chmod +x /usr/local/lib/python3.11/site-packages/copilot/bin/copilot || true

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run main.py when the container launches
# CMD ["python", "/app/src/main.py"]
CMD ["python", "-m", "src.main"]
