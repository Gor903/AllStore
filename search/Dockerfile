FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    # the model is downloaded on first use into a volume, not baked into the image: two
    # gigabytes in a layer would be rebuilt on every dependency change for no gain
    FASTEMBED_CACHE_PATH=/var/cache/fastembed \
    # the model weighs more than one file allows, so it ships as model.onnx plus a separate
    # model.onnx_data. onnxruntime refuses to follow the second one outside the first one's
    # directory, and the HuggingFace cache stores both as symlinks into a shared blob store —
    # with symlinks off the snapshot holds the real files side by side and the load succeeds
    HF_HUB_DISABLE_SYMLINKS=1
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /srv/app

FROM base AS dev
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS prod
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
RUN useradd --system --uid 1002 searchuser \
    && mkdir -p /var/cache/fastembed \
    && chown -R searchuser /srv/app /var/cache/fastembed
USER searchuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
