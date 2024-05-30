# app-borgmatic

This repository helps setting up backups using [borgmatic](https://torsion.org/borgmatic/) on a given server.

## HOWTO

1. Be root on the server
2. Install borgmatic:
```sh
apt install borgmatic
```
3. Clone this repo to `/etc/borgmatic`:
```sh
git clone https://github.com/redpencilio/app-borgmatic.git /etc/borgmatic
```
4. Create an SSH keypair for backups, without passphrase, and without overwriting existing keys:
```sh
yes n | ssh-keygen -f ~/.ssh/backups_rsa -P ''
```
5. Authorize the key on backup server.
   We're not using `ssh-copy-id` because some Ubuntu versions don't have SFTP mode of
   `ssh-copy-id`, which is needed by Hetzner's storage boxes:
```sh
sftp -P <port> -o StrictHostKeyChecking=accept-new <user>@<host> << EOF
mkdir .ssh
get .ssh/authorized_keys /tmp/authorized_keys
!grep -q "$(cat /root/.ssh/backups_rsa.pub)" /tmp/authorized_keys || cat /root/.ssh/backups_rsa.pub >> /tmp/authorized_keys
put /tmp/authorized_keys .ssh/authorized_keys
!rm /tmp/authorized_keys
bye
EOF
```
6. Initialize the borg repository:
```sh
borgmatic init --encryption repokey
```
7. Setup a crontab
