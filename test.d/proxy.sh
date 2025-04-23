cat << EOF > .env-test

EOF

set -xe
curl -sSf http://test.com/http://httpbin.org/get -v|grep httpbin.org
curl -sSf http://test.com/https://httpbin.org/get -v|grep httpbin.org
curl -sSf http://test.com/httpbin.org/get -v|grep httpbin.org