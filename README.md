# app-borgmatic

This repository helps setting up backups using [borgmatic](https://torsion.org/borgmatic/) on a given server, using `docker-compose`.
It includes a `borgmatic-exporter` container to export metrics for Prometheus.
The metrics are written to a text file in `./data/borgmatic-exporter/metrics/`, ready to be fed to a [node-exporter textfile collector](https://github.com/prometheus/node_exporter?tab=readme-ov-file#textfile-collector).

## Principles

This repository is to be cloned to, say, `/data/app-borgmatic`.
By default, Borgmatic expects a configurations files inside `/etc/borgmatic.d/`.
This directory is bind-mounted to `./data/borgmatic.d/`, so that the configuration can be added by hand.

## Per-app configuration

It is possible to use multiple configuration files with different configuration values, to backup different parts of the server with a different backup policy.
This is for example useful to apply different retentions for logs and backup dumps.

To use this, just add several `.yaml` files inside `./data/borgmatic.d/`.
Each invocation of `borgmatic` will apply these files independently, in sequence.

## Setup HOWTO

1. Be root on the server

2. Clone this repo to `/data/app-borgmatic`.

3. Create an SSH keypair for backups, without passphrase, and without overwriting existing keys:
```sh
yes n | ssh-keygen -f ~/.ssh/id_borgmatic -N ''
```

4. Authorize the key on backup server.
   We're not using `ssh-copy-id` because some Ubuntu versions don't have SFTP mode of
   `ssh-copy-id`, which is needed by Hetzner's storage boxes.

   **Note**: Adding the `command=...,restrict` part to the line containing the key prevents SFTP/SSH use for anything other than remote borg commands, which helps mitigate the situation where an attacker completely compromises the server:
```sh
sftp -P <port> -o StrictHostKeyChecking=accept-new <user>@<host> << EOF
mkdir .ssh
get .ssh/authorized_keys /tmp/authorized_keys
!grep -q "$(cat /root/.ssh/id_borgmatic.pub)" /tmp/authorized_keys || echo 'command="borg serve --umask=077 --info",restrict' $(cat /root/.ssh/id_borgmatic.pub) >> /tmp/authorized_keys
put /tmp/authorized_keys .ssh/authorized_keys
!rm /tmp/authorized_keys
bye
EOF
```
   Additional restrictions can be set, to restrict Borg to specific repositories, or force append-only mode:
```sh
command="borg serve --umask=077 --info --append-only --restrict-to-repository /home/something.borg/ --restrict-to-repository /home/something-else.borg/",restrict ssh-rsa ...
```

5. Create `./data/borgmatic.d/*.yaml` file(s) from the provided example:
```sh
cp config.example.yaml data/borgmatic.d/config.yaml
```
   Or if using multiple configuration files:
```sh
cp config.example.yaml data/borgmatic.d/main.yaml
cp config.example.yaml data/borgmatic.d/something.yaml
```

6. Modify it/them...

7. **MAKE SURE TO `chmod` THE RESULTING FILE(S)**, it/they will contain the passphrase:
```sh
for f in data/borgmatic.d/*.yaml; do
    chown root: "$f"; chmod 600 "$f"
done
```

8. Create a `docker-compose.override.yml`, and modify as needed:
```sh
cp docker-compose.override.example.yml docker-compose.override.yml
```

9. Copy the example crontab, and modify as needed:
```sh
cp crontab.txt data/borgmatic.d/
```

10. Copy the crontab for `borgmatic-exporter`, and modify if needed (by default metrics are written once per hour):
```sh
cp borgmatic-exporter_crontab.txt data/borgmatic-exporter/crontab.txt
```

11. Start the containers:
```sh
docker compose up -d
```

12. Initialize the borg repository (multiple repositories will be initialized as defined in configuration files):
```sh
docker compose exec borgmatic borgmatic init --encryption repokey
# if append-only is wanted:
docker compose exec borgmatic borgmatic init --encryption repokey --append-only
```

## Restore backups

To be able to use Borg's FUSE mount capacities, we need to add some settings to the `docker-compose` file.
These are bundled in `docker-compose.restore.yml`, including a volume mounted to a location on the host for restored files to go.

So to restore backups:

1. Stop the running `borgmatic` container:
```sh
docker compose down
```

2. Modify the `.env` to use `docker-compose.restore.yml` (the line is commented)

3. Start the new restore container:
```sh
docker compose up -d
```

4. Run a shell on the container and mount needed archive(s)
```sh
docker compose exec borgmatic bash
borgmatic mount --archive latest --mount-point /mnt
```

5. Copy/restore needed files to the bind mount defined in `docker-compose.restore.yml`:
```sh
cp /mnt/data/backups/foo /restore
```
   Database dumps made with the `postgresql_databases` or `mariadb_databases` hooks are in `/root/.borgmatic/postgresql_databases/localhost/`.
   But Borgmatic has restore commands to deal with the database dumps easily.

6. Unmount, exit and remove the restore container:
```sh
umount /mnt && exit
docker compose down
```

7. Don't forget to change the `.env` back to what it was, and to start the borgmatic container again.

## Include borgmatic metrics in a configured `node-exporter`

If the crontab for `borgmatic-exporter` was copied to `./data/borgmatic-exporter/crontab.txt`, metrics should be written to a text file, ready to be included in `node-exporter` through its `textfile` collector.

You will need to edit the `node-exporter`'s `docker-compose.yml` to add a volume and a matching command argument:

```yml
volumes:
  - ...
  - /data/app-borgmatic/data/borgmatic-exporter/metrics:/data/borgmatic-metrics:ro
command:
  - "--collector.textfile.directory=/data/borgmatic-metrics"
```
