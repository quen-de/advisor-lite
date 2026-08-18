FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
WORKDIR /app
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
RUN useradd --create-home advisor
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY api/src ./src
COPY api/etc ./etc
ENV PATH="/app/.venv/bin:$PATH" PORTFOLIO_PATH=/app/etc/portfolio.yaml
USER advisor
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD \
  python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/healthz')"
CMD ["uvicorn", "--factory", "advisor.web.app:create_app", "--host", "0.0.0.0", "--port", "8000"]
