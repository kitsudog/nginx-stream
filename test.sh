TARGET_HOST=${1:-127.0.0.1}
TARGET_PORT=${2:-8080}
TARGET_TLS_PORT=${3:-8443}
TARGET_PORT2=${4:-18080}
TARGET_DNS_PORT=${5:-1053}
TARGET=${TARGET_PORT}:${TARGET_HOST}
TARGET_TLS=${TARGET_TLS_PORT}:${TARGET_HOST}

IP=$(curl ifconfig.me -s)
set -xe
echo BIND_1=8080:183.2.172.185:443
curl "https://${TARGET_HOST}:${TARGET_PORT2}" -vk 2>&1|grep subject:|grep Baidu
echo BIND_2=udp@53:8.8.8.8:53
dig @${TARGET_HOST} -p ${TARGET_DNS_PORT} www.baidu.com 2>&1 > /dev/null
echo BIND_3=53:8.8.8.8:53
dig @${TARGET_HOST} -p ${TARGET_DNS_PORT} www.baidu.com 2>&1 > /dev/null
echo LISTEN_1=echo.com:httpbin.org/get?
curl "http://echo.com:${TARGET_PORT}" --resolve "echo.com:${TARGET}" -s|grep $IP > /dev/null
echo LISTEN_2=echo2.com:httpbin.org/get?
curl "http://echo2.com:${TARGET_PORT}" --resolve "echo2.com:${TARGET}" -s|grep $IP > /dev/null
# curl "https://echo2.com:${TARGET_TLS_PORT}" --resolve "echo2.com:${TARGET_TLS}" -sk|grep $IP > /dev/null
echo LISTEN_3=https@www.test.com:www.baidu.com
test $(curl "http://www.test.com:${TARGET_PORT}" --resolve "www.test.com:${TARGET}" -s|grep baidu.com|wc -l) = 0
echo LISTEN_4=https@www.test2.com:www.baidu.com
# test $(curl "https://www.test2.com:${TARGET_TLS_PORT}" --resolve "www.test2.com:${TARGET_TLS}" -sk|grep baidu.com|wc -l) = 0
echo FORWARD_1=www.test3.com:www.baidu.com
curl "http://www.test3.com:${TARGET_PORT}" --resolve "www.test3.com:${TARGET}" -si|head -n1|grep "HTTP/1.1 403 Forbidden"
echo REDIRECT_1=baidu.games=https://www.baidu.com/
curl "http://baidu.games:${TARGET_PORT}/123" --resolve "baidu.games:${TARGET}" -si|grep "Location: https://www.baidu.com/123"
echo REDIRECT_2=mode2.baidu.games=https://www.baidu.com/
curl "http://mode2.baidu.games:${TARGET_PORT}/123" --resolve "mode2.baidu.games:${TARGET}" -si|grep "Location: https://www.baidu.com/"
echo REDIRECT_3=mode3.baidu.games=https://www.baidu.com/
curl "http://mode3.baidu.games:${TARGET_PORT}/test1?a=b#b=1" --resolve "mode3.baidu.games:${TARGET}" -si|grep 'window.location'
echo succ
