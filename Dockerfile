# Step 1: Use an official lightweight Python image
FROM python:3.11-slim

# Step 2: Set the working directory inside the container
WORKDIR /app

# Step 3: Copy the requirements file and install dependencies
COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app

# Step 4: Copy the rest of the application code into the container
COPY app.py .
COPY app_meta/ ./app_meta/
# deploy.sh writes build_info.py before tarball; local builds: cp build_info.default.py build_info.py
COPY build_info.py .
COPY models/ ./models/
COPY utils/ ./utils/
COPY services/ ./services/
COPY routes/ ./routes/
COPY templates/ ./templates/
COPY static/ ./static/
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh \
    && chown -R app:app /app

# Step 5: Expose the port the app runs on
EXPOSE 5000

# Step 6: Run as non-root (entrypoint fixes /data ownership when started as root)
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn", "--workers", "2", "--timeout", "120", "--bind", "0.0.0.0:5000", "app:app"]
