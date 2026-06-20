# Use Playwright official python runtime as parent image
FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

# Set shell to bash
SHELL ["/bin/bash", "-c"]

# Set working directory
WORKDIR /app

# Install uv for dependency management
RUN pip install --no-cache-dir uv==0.5.11

# Copy project files
COPY pyproject.toml uv.lock ./

# Install dependencies into system Python using uv
RUN uv pip install --system -r pyproject.toml

# Copy application source code
COPY main.py ./

# Expose port (Cloud Run sets PORT env, defaults to 8080)
EXPOSE 8080

# Run the web service using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "0", "main:handler"]
