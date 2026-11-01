FROM python:3.14-alpine
WORKDIR /app
COPY workload.py load.py /app/
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["python", "/app/workload.py"]
