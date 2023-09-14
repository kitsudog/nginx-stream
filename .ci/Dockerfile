FROM kitsudo/nginx-python3:3.9
ENV UPSTREAM_PORT=81 \
    UPSTREAM_HOST=127.0.0.1
COPY start.sh task.sh start.py app.py /app/
WORKDIR /app
ENTRYPOINT ["/app/start.sh"]
