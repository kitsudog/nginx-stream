cat << EOF > .env-test
LISTEN_1=test1.com:httpbin.org
LISTEN_1_EX=TRUE
REPLACE_PATTERN=#httpbin.org#test.com#
EOF

set -xe
curl -sSf http://test1.com/get -v |grep test.com