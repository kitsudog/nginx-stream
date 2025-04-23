docker rm -f test
docker build -f .ci/Dockerfile -t test:v0.1 .
for line in $(find test.d -type f -iname '*.sh'|grep ${1:-sh})
do
  DIR_NAME=$(dirname $line)
  FILE=$(basename $line)
  FILE_NAME=$(echo $FILE|sed 's#\.sh##')

  head -n$(grep EOF $line -n|tail -n1|cut -d: -f1) $line >  tmp.sh
  sh tmp.sh

  :>test.out
  :>test.pcap
  TEST=$FILE_NAME docker-compose up --remove-orphans 2>&1 | sed "s#^test#${FILE_NAME}#"
  tail -n 1 test.out |grep fail
  if [ $? -eq 0 ];then
    cat test.out
    exit 1
  fi
done
echo over