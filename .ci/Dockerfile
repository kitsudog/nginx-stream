#FROM kitsudo/nginx-python3:3.10
FROM kitsudo/openresty-python3:3.10
RUN apk upgrade --update-cache -a && apk add --no-cache tcpdump curl autossh dumb-init && rm -rf /tmp/* /root/.cache
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt && rm -rf /root/.cache/pip
ENV TCPDUMP_DURATION=60 \
    PROXY_LISTEN_PORT=82 \
#    FILTER_EXPR="~c 200 ~ts json" \
#    MONGO_COLLECTION=record \
    KEEP_TIME=720 \
    UPSTREAM_PORT=81 \
    UPSTREAM_HOST=127.0.0.1 \
    TZ=Asia/Shanghai
COPY *.sh *.py /app/
COPY html/ /var/www/html/
COPY templates/ /app/templates/
COPY certs/ /etc/nginx/certs/
#VOLUME /var/cache/nginx
WORKDIR /app
ENTRYPOINT ["/app/start.sh"]
