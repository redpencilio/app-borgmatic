#!/bin/bash
DAYS=30

if [ $# -ne 1 ];then
    echo "Usage: "
    echo "      $0 [virtuoso-container-name]"
    exit -1;
fi

docker=`which docker`
if [ $? -ne 0 ]; then
    echo "ERROR: could not find docker executable";
    exit -1;
fi


virtuoso_container=$1
date=`date +%y%m%dT%H%M`
backup_name="virtuoso_backup_$date-"
$docker exec -i $virtuoso_container mkdir -p backups
$docker exec -i $virtuoso_container isql-v <<EOF
    exec('checkpoint');
		backup_context_clear();
		backup_online('$backup_name',30000,0,vector('backups'));
		exit;
EOF
$docker exec -i $virtuoso_container find /data/backups/ -name 'virtuoso_backup_*' -mtime +$DAYS -delete
