FROM docker.m.daocloud.io/library/python:3.11-slim
WORKDIR /app
ENV TZ=Asia/Shanghai PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ \
    flask==3.1.3 requests==2.32.5 openpyxl==3.1.5 gunicorn==23.0.0
COPY app.py import_data.py ./
COPY templates ./templates
COPY static ./static
COPY data ./data
RUN python import_data.py data/model.xlsx
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "2", "--timeout", "120", "app:app"]
