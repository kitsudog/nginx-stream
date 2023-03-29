#!/bin/sh
python3 /app/start.py || exit 1
cat ${CONFIG_FILE:-/etc/nginx/nginx.conf}|awk '{print NR"\t"$0}'
echo start task
if [ "${RELOAD:-FALSE}" = "TRUE" ];then
  echo RELOAD
  /app/task.sh &
fi
/docker-entrypoint.sh nginx -g "daemon off;"