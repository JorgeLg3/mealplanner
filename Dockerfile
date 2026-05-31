### 1 - BUILD STAGE ###
# Install uv
FROM python:3.14-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Use the system Python across both stages
ENV UV_PYTHON_DOWNLOADS=0

# Change the working directory to the `app` directory
WORKDIR /app

# Install dependencies
# Cache mount improve speed across builds
# --no-install-project --no-editable to not copy project (later step)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable --no-dev

# Copy the project into the intermediate image
COPY . /app

# Activate the virtual environment copied from the build stage.
ENV PATH="/app/.venv/bin:$PATH"

# env variables not available until runtime
RUN DEBUG=False SECRET_KEY=mytemporalkey ./manage.py collectstatic --noinput    

### 2 - DEPLOY STAGE ###
FROM python:3.14-slim-trixie

WORKDIR /app

# Prevent Python from buffering stdout/stderr so logs appear immediately.
ENV PYTHONUNBUFFERED=1

# Activate the virtual environment copied from the build stage.
ENV PATH="/app/.venv/bin:$PATH"

# Copy the environment and the source code
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app /app

EXPOSE 8000

# Run migrations and Gunicorn as the production WSGI server.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn django_project.wsgi:application --bind 0.0.0.0:8000"]