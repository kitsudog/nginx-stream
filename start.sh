#!/bin/sh
cat <<EOF
Usage: 
  LISTEN=80:192.168.1.1:80 BIND=80:192.168.1.1:80 ./start.sh

EOF

for i in `seq 100`;do
  LISTEN_EX=$(env|grep "^LISTEN_$i=")
  LISTEN_PROXY_HOST=$(env|grep "^LISTEN_PROXY_HOST_$i="|cut -d= -f2-)
  BIND_EX=$(env|grep "^BIND_$i=")
  if [ ! -z "${LISTEN_EX}" ];then
    if [ ! -z "${LISTEN_PROXY_HOST}" ];then
      LISTEN_EX=${LISTEN_EX}@${LISTEN_PROXY_HOST}
    fi 
    LISTEN="${LISTEN};${LISTEN_EX#*=}"
  fi
  if [ ! -z "${BIND_EX}" ];then
    BIND="${BIND}:${BIND_EX#*=}"
  fi
done

LISTEN=$(echo $LISTEN|sed 's#^;##')
BIND=$(echo $BIND|sed 's#^;##')

echo LISTEN=$LISTEN
echo BIND=$BIND

FILE=/etc/nginx/nginx.conf
cat <<EOF > $FILE
user  nginx;
worker_processes  auto;

error_log   /var/log/nginx/error.log notice;
pid         /var/run/nginx.pid;

events {
    worker_connections  10240;
}
http {
  resolver ${DNS:-8.8.8.8} valid=5 ipv6=off;
  include       /etc/nginx/mime.types;
  default_type  application/octet-stream;
  log_format  main  '\$remote_addr - \$remote_user [\$time_local] "\$request" '
                    '\$status \$body_bytes_sent "\$http_referer" '
                    '"\$http_user_agent" "\$http_x_forwarded_for"';

  access_log  /var/log/nginx/access.log  main;
  sendfile        on;
  #tcp_nopush     on;

  keepalive_timeout  65;
  # If we receive X-Forwarded-Proto, pass it through; otherwise, pass along the
  # scheme used to connect to this server
  map \$http_x_forwarded_proto \$proxy_x_forwarded_proto {
    default \$http_x_forwarded_proto;
    ''      \$scheme;
  }
  # If we receive X-Forwarded-Port, pass it through; otherwise, pass along the
  # server port the client connected to
  map \$http_x_forwarded_port \$proxy_x_forwarded_port {
    default \$http_x_forwarded_port;
    ''      \$server_port;
  }
  # If we receive Upgrade, set Connection to "upgrade"; otherwise, delete any
  # Connection header that may have been passed to this server
  map \$http_upgrade \$proxy_connection {
    default upgrade;
    '' close;
  }
  # Set appropriate X-Forwarded-Ssl header based on \$proxy_x_forwarded_proto
  map \$proxy_x_forwarded_proto \$proxy_x_forwarded_ssl {
    default off;
    https on;
  }
  gzip_types text/plain text/css application/javascript application/json application/x-javascript text/xml application/xml application/xml+rss text/javascript;
  # HTTP 1.1 support
  proxy_http_version 1.1;
  proxy_buffering off;
  proxy_set_header Host \$http_host;
  proxy_set_header Upgrade \$http_upgrade;
  proxy_set_header Connection \$proxy_connection;
  proxy_set_header X-Real-IP \$remote_addr;
  proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto \$proxy_x_forwarded_proto;
  proxy_set_header X-Forwarded-Ssl \$proxy_x_forwarded_ssl;
  proxy_set_header X-Forwarded-Port \$proxy_x_forwarded_port;
  proxy_set_header Proxy "";

  server {
    server_name _;
    server_tokens off;
    listen 80;
    return 503;
  }
EOF

for i in `seq 100`;do
  LISTEN_EX=$(env|grep "^LISTEN_$i=")
  SERVER_DNS_EX=$(env|grep "^LISTEN_DNS_$i=")
  if [ -z "${LISTEN_EX}" ];then
    continue
  fi
  line=${LISTEN_EX#*=}
  SERVER_DNS=${SERVER_DNS_EX#*=}
  # (https@)(listen:)dest(:port)(/url)(@proxy)
  EXP='\(\(https\)@\)\?\(\([^:@/]*\):\)\?\([^:@/]*\)\(:[[:digit:]]*\)\?\(/[^@]*\)\?\(@\(.*\)\)\?'
  PROTOCOL=$(echo $line|sed 's#'$EXP'#\2#')
  LISTEN_HOST=$(echo $line|sed 's#'$EXP'#\4#')
  HOST=$(echo $line|sed 's#'$EXP'#\5#')
  PORT=$(echo $line|sed 's#'$EXP'#\6#')
  URL=$(echo $line|sed 's#'$EXP'#\7#')
  PROXY_HOST=$(echo $line|sed 's#'$EXP'#\9#')
  
  cat <<EOF >> $FILE
  upstream LISTEN_$i {
    # for $LISTEN_EX
    server ${HOST}${PORT};
  }

  server {
    listen 80;
    server_name ${LISTEN_HOST:-_};
    ssl_verify_client off;
    $(test -z "$SERVER_DNS" || echo "resolver ${SERVER_DNS};") 

    location / {
      proxy_set_header Host ${PROXY_HOST:-\$proxy_host};
      proxy_set_header X-FROM ${LISTEN_HOST:-_};
      proxy_pass ${PROTOCOL:-http}://${HOST}${PORT}${URL};
      proxy_redirect default;
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection \$proxy_connection;
    }
  }

EOF
done

cat <<EOF >> $FILE
}

stream {
  log_format proxy '\$remote_addr [\$time_local] '
                 '\$protocol \$status \$bytes_sent \$bytes_received '
                 '\$session_time -> \$upstream_addr '
                 '\$upstream_bytes_sent \$upstream_bytes_received \$upstream_connect_time';
  access_log /var/log/nginx/access.log proxy buffer=32k;
  open_log_file_cache off;
EOF
echo ${BIND}|grep '[^,;]*' -o|while read line
do
  udp=${line%@*}
  line2=$(echo $line|sed 's#[^:]##g')
  if [ "$udp" = "udp" ];then
    udp=" udp";
    line=${line#*@}
  else
    udp=""
  fi
  if [ ${#line2} -ge 2 ];then
    LISTEN_PORT=$(echo $line|cut -d: -f1)
    HOST=$(echo $line|cut -d: -f2)
    PORT=$(echo $line|cut -d: -f3)
  elif [ ${#line2} -eq 1 ];then
    HOST=$(echo $line|cut -d: -f1)
    PORT=$(echo $line|cut -d: -f2)
    LISTEN_PORT=$PORT
  elif [ ${#line2} -eq 0 ];then
    HOST=$(echo $line|cut -d: -f1)
    PORT=80
    LISTEN_PORT=80
  fi
  
  cat <<EOF >> $FILE
  server {
    listen $LISTEN_PORT${udp};
    proxy_connect_timeout ${CONNECT_TIMEOUT:-3}s;
    proxy_timeout ${TIMEOUT:-10}s;
    proxy_pass $HOST:$PORT;
  }

EOF
done

cat <<EOF >> $FILE
}
EOF
cat $FILE|awk '{print NR"\t"$0}'
echo start task
/app/task.sh &
nginx -g "daemon off;"
