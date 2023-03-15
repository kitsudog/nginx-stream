FROM nginx:1.20
RUN apt update && apt install --no-install-recommends --no-install-suggests -y curl telnet ncat python3-minimal wget \
  && apt-get remove --purge --auto-remove -y && rm -rf /var/lib/apt/lists/*
COPY start.sh task.sh start.py /app/
WORKDIR /app
ENTRYPOINT ["/app/start.sh"]
