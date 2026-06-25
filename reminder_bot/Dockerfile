FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py database.py scheduler.py vote_system.py ./

# Create data directory
RUN mkdir -p /app/data

# Set environment variable
ENV DATABASE_PATH=/app/data/reminders.db

# Run the bot
CMD ["python", "main.py"]
