for line in $(find test.d -type f -iname '*.sh'|grep ${1:-sh})
do
  DIR_NAME=$(dirname $line)
  FILE=$(basename $line)
  FILE_NAME=$(echo $FILE|sed 's#\.sh##')

  head -n$(grep EOF $line -n|tail -n1|cut -d: -f1) $line >  tmp.sh
  sh tmp.sh

  :>test.out
  :>test.pcap
  docker run --rm -it \
    --env-file `pwd`/.env-test \
    --add-host test.com:127.0.0.1 \
    --add-host test1.com:127.0.0.1 \
    --add-host test2.com:127.0.0.1 \
    --add-host test3.com:127.0.0.1 \
    -v $(realpath $line):/test.sh \
    -v `pwd`/test.out:/test.out \
    -v `pwd`/test.pcap:/test.pcap \
    -v `pwd`/keys=/keys \
    --name test local:v0.1 | sed "s#^#[${FILE_NAME}]: #" 2>&1
  tail -n 1 test.out |grep fail
  if [ $? -eq 0 ];then
    cat test.out
    exit 1
  fi
done
echo over