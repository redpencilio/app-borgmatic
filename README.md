# app-borgmatic

This repository helps setting up backups using [borgmatic](https://torsion.org/borgmatic/) on a given server, using `docker-compose`.
It includes a `borgmatic-exporter` container to export metrics for Prometheus.
The metrics are written to a text file in `./data/borgmatic-exporter/metrics/`, ready to be fed to a [node-exporter textfile collector](https://github.com/prometheus/node_exporter?tab=readme-ov-file#textfile-collector).

## Getting started

### Principles

This repository is to be cloned to, say, `/data/app-borgmatic`.
By default, Borgmatic expects a configurations files inside `/etc/borgmatic.d/`.
This directory is bind-mounted to `./config/borgmatic.d/`, so that the configuration can be added by hand.

### Per-app configuration

It is possible to use multiple configuration files with different configuration values, to backup different parts of the server with a different backup policy.
This is for example useful to apply different retentions for logs and backup dumps.

To use this, just add several `.yaml` files inside `./config/borgmatic.d/`.
Each invocation of `borgmatic` will apply these files independently, in sequence.

## How-to guides

### Setup

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
touch -ac .ssh/authorized_keys
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

5. Create `./config/borgmatic.d/*.yaml` file(s) from the provided example:
```sh
cp config.example.yaml config/borgmatic.d/config.yaml
```
   Or if using multiple configuration files:
```sh
cp config.example.yaml config/borgmatic.d/main.yaml
cp config.example.yaml config/borgmatic.d/something.yaml
```

6. Modify it/them...

7. **MAKE SURE TO `chmod` THE RESULTING FILE(S)**, it/they will contain the passphrase:
```sh
for f in config/borgmatic.d/*.yaml; do
    chown root: "$f"; chmod 600 "$f"
done
```

8. Create a `docker-compose.override.yml`, and modify as needed:
```sh
cp docker-compose.override.example.yml docker-compose.override.yml
```

9. Crontabs for both borgmatic and borgmatic-exporter are set using environment variables.

10. Start the containers:
```sh
docker compose up -d
```

11. Initialize the borg repository (multiple repositories will be initialized as defined in configuration files):
```sh
docker compose exec borgmatic borgmatic init --encryption repokey
# if append-only is wanted:
docker compose exec borgmatic borgmatic init --encryption repokey --append-only
```

### Prevent locking yourself out

The repository encryption uses [repokey](https://borgbackup.readthedocs.io/en/stable/usage/init.html#encryption-mode-tldr), which stores the encryption in the repository, and uses the passphrase from the config file for decryption.
This means there are two items you should keep somewhere safe:

- the passphrase
- the key, needs to be exported:
```bash
docker compose exec borgmatic borgmatic key export
```
  yes, that's *two* `borgmatic borgmatic` in a row: the first is the `docker-compose` service, the second issues a `borgmatic` command within that container.

### Restore backups on the client server

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

6. Unmount, exit and remove the restore container:
```sh
umount /mnt && exit
docker compose down
```

7. Don't forget to change the `.env` back to what it was, and to start the borgmatic container again.

### Restore backups on a local machine

As long as you have the passphrase and SSH key for the repository, you can inspect/export/mount the borgmatic repository from any machine.

Just install Borgmatic (using this repo or locally on your machine) and use the same configuration file(s) as the one configured for the client server.

You then have access to, for example:
- `borgmatic list`
- `borgmatic info`
- `borgmatic extract ...`
- `borgmatic mount ...`

### Include borgmatic metrics in a configured `node-exporter`

Metrics are written to a text file, ready to be included in `node-exporter` through its `textfile` collector.

You will need to edit the `node-exporter`'s `docker-compose.yml` to add a volume and a matching command argument:

```yml
volumes:
  - ...
  - /data/app-borgmatic/data/borgmatic-exporter/metrics:/data/borgmatic-metrics:ro
command:
  - "--collector.textfile.directory=/data/borgmatic-metrics"
```

### Running commands inside a container

The syntax when running a `borgmatic` or `borg` command inside a container implies multiple `borgmatic` next to each other.
The first `borgmatic` is the service name, the second is the `borgmatic` command from inside the container.

Here are some examples:
- Run `borgmatic` inside the `borgmatic` container:
```bash
docker compose exec borgmatic borgmatic ...
```
- If multiple config files and/or repositories are set, you will need to specify which repository for some commands:
```bash
docker compose exec borgmatic borgmatic list --repository foo
```
- If a `borg` command isn't natively handled by `borgmatic`, you can issue the `borg` subcommand to arbitrarily run a `borg` command.
  This has the advantage of using the borgmatic configuration, simplifying the underlying `borg` command:
```bash
docker compose exec borgmatic borgmatic borg ...
```

## Reference

- [https://torsion.org/borgmatic/](https://torsion.org/borgmatic/)
- [https://github.com/borgmatic-collective/docker-borgmatic](https://github.com/borgmatic-collective/docker-borgmatic)
- [https://github.com/maxim-mityutko/borgmatic-exporter](https://github.com/maxim-mityutko/borgmatic-exporter)
