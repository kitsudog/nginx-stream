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
if [ "${RECORD}" = "TRUE" ];then
    mkdir -p /pcap
    tcpdump -G ${TCPDUMP_DURATION:-60} tcp -i eth0 -s0 -w /pcap/data-%F_%H%M.pcap &
    # 默认清理12h前的
    KEEP_TIME=${KEEP_TIME:-720}
    sh -c "while true;do sleep 60;find /pcap -type f -mmin ${KEEP_TIME}|xargs -r rm -v;done;" &
    if [ "${FILTER_EXPR}" ];then
        python3 /app/pcaper.py &
    fi
fi
if [ "${EX}" == "TRUE" ];then
    python3 /app/app.py &
fi
/docker-entrypoint.sh nginx -g "daemon off;"