#!/bin/bash
connection_string=$1
if [[ $connection_string =~ ^([^@]+)@([^:]+):?(.*)$ ]]; then
  user="${BASH_REMATCH[1]}"
  host="${BASH_REMATCH[2]}"
  port="${BASH_REMATCH[3]:-23}"
else
  echo ""
  echo "Invalid connection string format. Expected user@host:port"
  exit 1
fi

echo ""
echo "Generating SSH key pair..."
yes n | ssh-keygen -t rsa -f /project/ssh-keys/id_borgmatic -N '' > /dev/null

echo "Granting access for generated SSH key on backup server $user@$host"

sftp -q -P $port -o StrictHostKeyChecking=accept-new $user@$host > /dev/null 2>&1 << EOF
mkdir .ssh
get .ssh/authorized_keys /tmp/authorized_keys
!touch -a /tmp/authorized_keys
!grep -q "$(cat /project/ssh-keys/id_borgmatic.pub)" /tmp/authorized_keys || echo 'command="borg serve --umask=077 --info",restrict' $(cat /project/ssh-keys/id_borgmatic.pub) >> /tmp/authorized_keys
put /tmp/authorized_keys .ssh/authorized_keys
!rm /tmp/authorized_keys
bye
EOF

if [ $? -eq 0 ]; then
  echo "Successfully generated SSH key with access to backup server $user@$host"
  echo ""
  echo "Move the generated SSH key files to ~/.ssh/ folder of the server that needs a backup."
  echo "> mv ./ssh-keys/id_borgmatic{,.pub} ~/.ssh/"
else
  echo "Authorizing key on backup server $user@$host failed."
fi
