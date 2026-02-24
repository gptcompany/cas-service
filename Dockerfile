FROM sagemath/sagemath:latest

USER root

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY cas_service/ cas_service/

RUN chown -R sage:sage /app

EXPOSE 8769

USER sage
CMD ["/app/.venv/bin/python", "-m", "cas_service.main"]
