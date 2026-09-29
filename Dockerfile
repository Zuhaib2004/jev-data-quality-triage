FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 triage && mkdir /data && chown triage /data
COPY examples ./examples
USER triage
ENTRYPOINT ["jev-triage"]
CMD ["examples/customers.csv", "--output", "/data/runs"]
