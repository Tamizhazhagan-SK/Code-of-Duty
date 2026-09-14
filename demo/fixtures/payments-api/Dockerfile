FROM python:3.12-slim
WORKDIR /app
# Copy only what the service needs: `COPY . .` would sweep in .env, .git and local secrets.
COPY src/ ./src/
ENV PAYMENTS_API_TOKEN={{gen:base62:32}}
CMD ["python", "-m", "payments"]
