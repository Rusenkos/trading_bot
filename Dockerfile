FROM python:3.10.12

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p data logs reports

# Default command runs the help
CMD ["python", "main.py"]