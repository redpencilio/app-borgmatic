#!/bin/bash

# Argument validation and parsing
operation=$1
connection_string=$2
if [[ $connection_string =~ ^([^@]+)@([^:]+):?(.*)$ ]]; then
  user="${BASH_REMATCH[1]}"
  host="${BASH_REMATCH[2]}"
  port="${BASH_REMATCH[3]:-23}"
else
  echo ""
  echo "Invalid connection string format '$connection_string'. Expected user@host:port."
  exit 1
fi

case $operation in
  "add") # Optionally generate SSH key and authorize it on remote server
    echo ""

    if [ -f /project/ssh-keys/id_borgmatic.pub ]; then
      echo "SSH key id_borgmatic.pub found in ./ssh-keys"
    else
      echo "Generating SSH key pair..."
      yes n | ssh-keygen -t rsa -f /project/ssh-keys/id_borgmatic -N '' > /dev/null
    fi

    echo "Granting access for SSH key on backup server $user@$host"
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
      echo "Successfully granted access to backup server $user@$host"
      echo ""
      echo "Move the SSH key files to ~/.ssh/ folder of the server that needs a backup."
      echo "> mv ./ssh-keys/id_borgmatic{,.pub} ~/.ssh/"
    else
      echo "Authorizing SSH key on backup server $user@$host failed."
    fi
    ;;

  "rm") # Remove SSH key from remote server
    echo ""
    if [ -f /project/ssh-keys/id_borgmatic.pub ]; then
      echo "SSH key id_borgmatic.pub found in ./ssh-keys"
    else
      echo "Please provide the SSH key pair to remove in ./ssh-keys/id_borgmatic{,.pub}"
      exit 1
    fi

    echo "Removing access for SSH key on backup server $user@$host"
    sftp -q -P $port -o StrictHostKeyChecking=accept-new $user@$host > /dev/null 2>&1 << EOF
mkdir .ssh
get .ssh/authorized_keys /tmp/authorized_keys
!touch -a /tmp/authorized_keys
!grep -v "$(cat /project/ssh-keys/id_borgmatic.pub)" /tmp/authorized_keys > /tmp/authorized_keys_updated
!mv /tmp/authorized_keys_updated /tmp/authorized_keys
put /tmp/authorized_keys .ssh/authorized_keys
!rm /tmp/authorized_keys
bye
EOF

    if [ $? -eq 0 ]; then
      echo "Successfully removed access from backup server $user@$host"
    else
      echo "Removing SSH key from backup server $user@$host failed."
    fi

    ;;
  *)
    echo "Unknown option $operation. Must be one of 'add' or 'rm'."
    ;;
esac
