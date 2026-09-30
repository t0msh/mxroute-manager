FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app

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

EXPOSE 5000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["gunicorn", "--workers", "2", "--timeout", "120", "--bind", "0.0.0.0:5000", "app:app"]
