FROM python:3.12-slim
WORKDIR /app
COPY . .
ENV PAYMENTS_API_TOKEN={{gen:base62:32}}
CMD ["python", "-m", "payments"]
