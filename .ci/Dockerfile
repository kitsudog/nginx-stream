FROM kitsudo/nginx-python3:3.9
RUN apk upgrade --update-cache -a && apk add --no-cache tcpdump curl && rm -rf /tmp/* /root/.cache
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt && rm -rf /root/.cache/pip
ENV TCPDUMP_DURATION=60 \
    UPSTREAM_PORT=81 \
    UPSTREAM_HOST=127.0.0.1
COPY *.sh *.py /app/
WORKDIR /app
ENTRYPOINT ["/app/start.sh"]
