FROM python:3.12-slim
WORKDIR /app
COPY app/ /app/
RUN python3 -c "import seed; seed.build('/tmp/probe.db')" && rm /tmp/probe.db
