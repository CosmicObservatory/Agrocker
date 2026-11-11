FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.7 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
COPY packages ./packages
RUN uv sync --frozen --package dashboard --no-dev

RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /app/data && chown -R app:app /app/data
USER app

ENV DB_DIR=/app/data
EXPOSE 8050
CMD ["agro-dashboard"]
