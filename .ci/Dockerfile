FROM nginx:1.20
RUN apt update && apt install --no-install-recommends --no-install-suggests -y curl telnet ncat \
  && apt-get remove --purge --auto-remove -y && rm -rf /var/lib/apt/lists/*
COPY start.sh task.sh /app/
ENTRYPOINT ["/app/start.sh"]
