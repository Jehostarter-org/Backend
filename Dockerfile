FROM python:3.12-slim

# Install system deps (GDAL for GeoDjango + PostgreSQL client)
RUN apt-get update && apt-get install -y \
    libgdal-dev binutils libproj-dev \
    gdal-bin postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL env
ENV GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so

# Set work directory
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Run migrations and collectstatic at startup
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && daphne -b 0.0.0.0 -p 8000 backend.asgi:application"]
