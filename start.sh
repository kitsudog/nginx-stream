#!/bin/sh
python3 /app/start.py
cat ${CONFIG_FILE:-/etc/nginx/nginx.conf}|awk '{print NR"\t"$0}'
echo start task
/app/task.sh &
nginx -g "daemon off;"
