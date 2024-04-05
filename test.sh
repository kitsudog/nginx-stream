TARGET_HOST=${1:-127.0.0.1}
TARGET_PORT=${2:-80}
TARGET_TLS_PORT=${3:-443}
TARGET=${TARGET_PORT}:${TARGET_HOST}
TARGET_TLS=${TARGET_TLS_PORT}:${TARGET_HOST}

IP=$(curl ifconfig.me -s)
set -xe
# LISTEN_1=echo.com:httpbin.org/get?
curl "http://echo.com:${TARGET_PORT}" --resolve "echo.com:${TARGET}" -s|grep $IP > /dev/null
# LISTEN_2=echo2.com:httpbin.org/get?
curl "http://echo2.com:${TARGET_PORT}" --resolve "echo2.com:${TARGET}" -s|grep $IP > /dev/null
curl "https://echo2.com:${TARGET_TLS_PORT}" --resolve "echo2.com:${TARGET_TLS}" -sk|grep $IP > /dev/null
# LISTEN_3=https@www.test.com:www.baidu.com
test $(curl "http://www.test.com:${TARGET_PORT}" --resolve "www.test.com:${TARGET}" -s|grep baidu.com|wc -l) = 0
# LISTEN_4=https@www.test2.com:www.baidu.com
test $(curl "https://www.test2.com:${TARGET_PORT}" --resolve "www.test2.com:${TARGET}" -sk|grep baidu.com|wc -l) = 0
# REDIRECT_1=baidu.games=https://www.baidu.com/
curl "http://baidu.games:${TARGET_PORT}/123" --resolve "baidu.games:${TARGET}" -si|grep "Location: https://www.baidu.com/123"
# REDIRECT_2=mode2.baidu.games=https://www.baidu.com/
curl "http://mode2.baidu.games:${TARGET_PORT}/123" --resolve "mode2.baidu.games:${TARGET}" -si|grep "Location: https://www.baidu.com/"
# REDIRECT_3=mode3.baidu.games=https://www.baidu.com/
curl "http://mode3.baidu.games:${TARGET_PORT}/123?a=b#b=1" --resolve "mode3.baidu.games:${TARGET}" -si|grep 'window.location'
echo succ
