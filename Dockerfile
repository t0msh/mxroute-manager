# Step 1: Use an official lightweight Python image
FROM python:3.11-slim

# Step 2: Set the working directory inside the container
WORKDIR /app

# Step 3: Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Step 4: Copy the rest of the application code into the container
COPY app.py .
COPY audit_log.py .
COPY dns_health.py .
COPY templates/ ./templates/
COPY static/ ./static/

# Step 5: Expose the port the app runs on
EXPOSE 5000

# Step 6: Run the app using Gunicorn bound to all network interfaces
CMD ["gunicorn", "--timeout", "60", "--bind", "0.0.0.0:5000", "app:app"]
