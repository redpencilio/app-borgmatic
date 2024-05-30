# app-borgmatic

This repository helps setting up backups using [borgmatic](https://torsion.org/borgmatic/) on a given server.

## HOWTO

1. Be root on the server
2. Install borg and borgmatic:
```sh
apt install borgbackup pipx
pipx ensurepath && source ~/.bashrc
pipx install borgmatic
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
6. Create a local `config.yaml` file from the provided example:
```sh
cp /etc/borgmatic/config.example.yaml /etc/borgmatic/config.yaml
```
7. Modify it...
8. **MAKE SURE TO `chmod` THE RESULTING FILE**, it will contain the passphrase:
```sh
chown root: /etc/borgmatic/config.yaml && chmod 600 /etc/borgmatic/config.yaml
```
9. Initialize the borg repository:
```sh
borgmatic init --encryption repokey
```
10. Setup a crontab:
```sh
cp /etc/borgmatic/borgmatic.cron /etc/cron.d/borgmatic # and modify if needed
```

## Why install using `pipx`?

Previous versions of this deployment used the Debian/Ubuntu packages, which are older versions.
With `borgmatic` 1.6, 1.7, and especially 1.8, changes in the configuration file have been made.
In particular, the way we use includes to be able to use a `.gitignore`d config file isn't possible in versions from the packages.
