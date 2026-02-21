FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    git \
    curl \
    bash \
    supervisor \
    apt-transport-https \
    ca-certificates \
    gnupg \
    dnsutils

RUN curl -sLf --retry 3 --tlsv1.2 --proto "=https" \
       'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' \
       | gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" \
       > /etc/apt/sources.list.d/doppler-cli.list \
    && apt-get update && apt-get install -y doppler \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for frontend build
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY main.py catalog.py api.py wrapper.sh ./
COPY targets.yaml users.yaml schedule.yaml ./

# Copy config files
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create directories that cron and logs will need
RUN mkdir -p /etc/cron.d /var/log/supervisor

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
