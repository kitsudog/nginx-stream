#!/bin/sh
python3 /app/start.py || exit 1
cat ${CONFIG_FILE:-/etc/nginx/nginx.conf}|awk '{print NR"\t"$0}'
echo start task
if [ "${RELOAD:-FALSE}" = "TRUE" ];then
    echo RELOAD
    /app/task.sh &
fi
if [ $# -gt 0 ];then
    $@
    exit $?
fi
if [ -n "${REPLACE}" ] || [ -n "${REPLACE_PATTERN}" ]; then
    export UPSTREAM_FILTER="replace"
    export EX=TRUE
fi
if [ "${EX}" == "TRUE" ];then
    python3 /app/app.py &
fi
/docker-entrypoint.sh nginx -g "daemon off;"