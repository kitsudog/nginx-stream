cat << EOF > .env-test
LISTEN_1=test1.com:www.baidu.com
LISTEN_2=https@test2.com:www.baidu.com
EOF

set -xe
curl -sSf http://test1.com |grep www.baidu.com > /dev/null
curl -sSf http://test2.com |grep www.baidu.com > /dev/null