# app-borgmatic

This repository helps setting up backups using [borgmatic](https://torsion.org/borgmatic/) on a given server.

## Principles

This repository is to be cloned to `/etc/borgmatic`.
By default, Borgmatic expects a configuration file at `/etc/borgmatic/config.yaml`.
This file is in `.gitignore`, so that it can be configured by hand.

## Per-app configuration

It is also possible to use multiple configuration files with different configuration values, to backup different parts of the server with a different backup policy.
This is for example useful to apply different retentions for logs and backup dumps.

To use this, instead of `/etc/borgmatic/config.yaml`, you should write multiple files in `/etc/borgmatic.d/*.yaml`.
Each invocation of `borgmatic` will apply these files independently, in sequence.

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
   `ssh-copy-id`, which is needed by Hetzner's storage boxes.

   **Note**: Adding the `command=...,restrict` part to the line containing the key prevents SFTP/SSH use for anything other than remote borg commands, which helps mitigate the situation where an attacker completely compromises the server:
```sh
sftp -P <port> -o StrictHostKeyChecking=accept-new <user>@<host> << EOF
mkdir .ssh
get .ssh/authorized_keys /tmp/authorized_keys
!grep -q "$(cat /root/.ssh/backups_rsa.pub)" /tmp/authorized_keys || echo 'command="borg serve --umask=077 --info",restrict' $(cat /root/.ssh/backups_rsa.pub) >> /tmp/authorized_keys
put /tmp/authorized_keys .ssh/authorized_keys
!rm /tmp/authorized_keys
bye
EOF
```
   Additional restrictions can be set, to restrict Borg to specific repositories, or force append-only mode:
```sh
command="borg serve --umask=077 --info --append-only --restrict-to-repository /home/something.borg/ --restrict-to-repository /home/something-else.borg/",restrict ssh-rsa ...
```
6. Create a local `config.yaml` file from the provided example:
```sh
cp /etc/borgmatic/config.example.yaml /etc/borgmatic/config.yaml
```
   Or if using multiple configuration files:
```sh
mkdir -p /etc/borgmatic.d
cp /etc/borgmatic/config.example.yaml /etc/borgmatic.d/main.yaml
cp /etc/borgmatic/config.example.yaml /etc/borgmatic.d/something.yaml
```
7. Modify it/them...
8. **MAKE SURE TO `chmod` THE RESULTING FILE(S)**, it/they will contain the passphrase:
```sh
for f in /etc/borgmatic/config.yaml /etc/borgmatic.d/*.yaml; do
    chown root: "$f"; chmod 600 "$f"
done
```
9. Initialize the borg repository (multiple repositories will be initialized as defined in configuration files):
```sh
borgmatic init --encryption repokey
# if append-only is wanted:
borgmatic init --encryption repokey --append-only
```
10. Setup a crontab:
```sh
cp /etc/borgmatic/borgmatic.cron /etc/cron.d/borgmatic # and modify if needed
```

## Why install using `pipx`?

Previous versions of this deployment used the Debian/Ubuntu packages, which are older versions.
With `borgmatic` 1.6, 1.7, and especially 1.8, changes in the configuration file have been made.
In particular, the way we use includes to be able to use a `.gitignore`d config file isn't possible in versions from the packages.
