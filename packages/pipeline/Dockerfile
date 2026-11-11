FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# uv_build necesita las fuentes para resolver los paquetes del workspace
COPY pyproject.toml uv.lock ./
COPY packages ./packages
RUN uv sync --frozen --package pipeline --no-dev

RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /app/data && chown -R app:app /app/data
USER app

ENV DB_DIR=/app/data
CMD ["agro-pipeline", "all"]
