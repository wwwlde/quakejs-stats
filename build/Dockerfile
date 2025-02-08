# Use official Python image (slim version to reduce size)
FROM python:3.12.2-slim

# Set working directory
WORKDIR /app

# Copy project files (including Python code)
COPY ./code /app

# Copy the requirements file separately to ensure better caching
COPY ./requirements.txt /app/

# Ensure the default database directory exists
RUN mkdir -p /app/db

# Install dependencies, including supervisord
RUN pip install --no-cache-dir -r requirements.txt

# Create a directory for supervisord logs
RUN mkdir -p /var/log/supervisor

# Expose Flask port
EXPOSE 5000

# Copy supervisord configuration
COPY supervisord.conf /etc/supervisord.conf

# Set supervisord as the main process
CMD ["supervisord", "-c", "/etc/supervisord.conf"]
