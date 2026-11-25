FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install C, C++, Node.js, Go compilers and build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    nodejs \
    golang-go \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Rust toolchain with system-wide access
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path \
    && chmod -R a+rwx /usr/local/rustup /usr/local/cargo

# Security: Non-root user (UID 1000 required for Hugging Face Spaces)
RUN useradd -m -u 1000 appuser
USER appuser
ENV HOME=/home/appuser
ENV PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /home/appuser/app

# Install Python dependencies
COPY --chown=appuser:appuser requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application source
COPY --chown=appuser:appuser . .

# Expose port (7860 for Hugging Face Spaces)
EXPOSE 7860

CMD ["uvicorn", "backend.server.server:app", "--host", "0.0.0.0", "--port", "7860"]
