# app-borgmatic

This repository helps setting up backups using [borgmatic](https://torsion.org/borgmatic/) on a given server, using `docker compose`.

## Getting started

Clone this repository on the server that needs to be backed up:

``` bash
git clone https://github.com/redpencilio/app-borgmatic.git
```

Ensure [mu-cli](https://github.com/mu-semtech/mu-cli/) is available on the server.

Navigate to the cloned repository:

``` bash
cd app-borgmatic
```

### Setup SSH key pair to connect to the remote storage box (only once)
Generate an SSH key pair using mu-cli. The key will be authorized on the remote storage box. Therefore you will need to enter the user's password of the storage box interactively.

``` bash
mu script project-scripts ssh-key add <user>@<host>:<port>
```

Next, move the generated SSH key pair to the server's `.ssh/` directory:

``` bash
rm -r ~/.ssh/id_borgmatic/ ; mv id_borgmatic{,.pub} ~/.ssh/
```

Borgmatic is now authorized to execute `borg` commands on the remote storage box using the generated SSH key pair `~/.ssh/id_borgmatic`.

This step needs to be executed only once during the initial setup of the backups. It doesn't need to be repeated in the future when new applications are added to the backup config.

### Generate Borgmatic config to backup a semantic.works application (once per application)
Generate a Borgmatic configuration for the application that needs to be backed up using mu-cli.

``` bash
mu script project-scripts generate-backup-config app <user>@<host>:<port> <hostname> <app-name>
```

E.g.
``` bash
mu script project-scripts generate-backup-config app u1234-sub1@u1234.your-storagebox.de:23 abb-croco app-mandatendatabank
```

The script will generate a new config in `./config/borgmatic.d/<app-name>.yml` and update `docker-compose.override.yml` accordingly.

Open the config file and make sure `source_directories` contain the folders that need to be backed up.

Next, (re)up the Borgmatic stack:

``` bash
docker compose up -d
```

Initialize the backup repository for the application:

``` bash
docker compose exec borgmatic borgmatic init --repository <app-name> --encryption repokey --append-only
```

Finally, export the repository key and store it somewhere save together with the passphrase generate by the `generate-backup-config` script. You will need the key and passphrase to be able to restore backups.

``` bash
docker compose exec borgmatic borgmatic key export --repository <app-name>
```

This step needs to be repeated for each application that requires a backup. For backups of app-http-logger, see [How to backup app-http-logger](#how-to-backup-app-http-logger).

## How-to guides
### How to change the backup frequency
Change the backup frequency by updating the `BACKUP_CRON` environment variable on the `borgmatic` service in `docker-compose.yml`.

This pattern applies on all repositories configured in `./config/borgmatic.d`. It's currently not possible to configure a different pattern per backup repository.

Next, up the stack again:

``` bash
docker compose up -d
```

### How to backup app-http-logger
Generate a config to backup HTTP logs generated by app-http-logger using mu-cli:

``` bash
mu script project-scripts generate-backup-config http-log <user>@<host>:<port> <hostname> <app-name>
```

E.g.
``` bash
mu script project-scripts generate-backup-config http-log u1234-sub1@u1234.your-storagebox.de:23 abb-croco app-http-logger
```

The script will generate a new config in `./config/borgmatic.d/<app-name>.yml` and update `docker-compose.override.yml` accordingly.

Next, (re)up the Borgmatic stack:

``` bash
docker compose up -d
```

Initialize the backup repository for the application:

``` bash
docker compose exec borgmatic borgmatic init --repository app-http-logger --encryption repokey --append-only
```

Finally, export the repository key and store it somewhere save together with the passphrase generate by the `generate-backup-config` script. You will need the key and passphrase to be able to restore backups.

``` bash
docker compose exec borgmatic borgmatic key export --repository app-http-logger
```

### How to access a backup from your local machine
This how-to guide assumes `docker-compose.dev.yml` is automatically taken into account on your local machine.

First, we need to make sure we can access the remote backup server from our local machine. If you already have an SSH key with access to the storage box, put the key pair in `./ssh-keys/id_borgmatic{,.pub}`. Otherwise, we will generate an SSH key and grant ourselves (temporary) access. Therefore, you will need to enter the password of the storage box interactively.
``` bash
mu script project-scripts ssh-key add <user>@<host>:<port>
```

Next, we will generate a minimalistic Borgmatic configuration to access the remote backup repository.

``` bash
mu script project-scripts generate-restore-config <repository_path> <passphrase>
```

E.g. 

``` bash
mu script project-scripts generate-restore-config ssh://u1234-sub1@u1234.your-storagebox.de:23/./abb-croco-app-mandatendatabank.borg my-secret-passphrase
```

Next, start the application stack.

``` bash
docker compose up -d
```

You should now be able to access the backup repository on the remote server via the `borgmatic-restore` service.

``` bash
docker compose exec borgmatic-restore borgmatic list
```

In order to restore files, `exec` in the `borgmatic-restore` service:

``` bash
docker compose exec borgmatic-restore bash
```

Inside the container, mount a repository archive (e.g. `latest`):

``` bash
borgmatic mount --archive latest --mount-point /mnt
```

You can now inspect the files in `/mnt/`. Use the `/restore` folder in the container to copy files to `./data/restore` on the host machine.

E.g.
``` bash
cp /mnt/data/app-mandatendatabank/docker-compose.yml /restore
```
s
When done, unmount the archive and exit the container.

``` bash
umount /mnt && exit
```

Don't forget, when you're finished, to remove the SSH key access from the backup server again:

``` bash
mu script project-scripts ssh-key rm <user>@<host>:<port>
```

### How to include borgmatic metrics in a configured `node-exporter`
This how-to-guide assumes a metrics stack including a `node-exporter` service is running on your server (e.g. `/data/metrics`). How to setup such a stack is explained in [app-server-monitor](https://github.com/redpencilio/app-server-monitor?tab=readme-ov-file#how-to-add-a-server-to-be-monitored).

The app-borgmatic stack includes a `borgmatic-exporter` container to export metrics for Prometheus. The metrics are written to a text file in `./data/borgmatic-exporter/metrics/`, ready to be fed to a [node-exporter textfile collector](https://github.com/prometheus/node_exporter?tab=readme-ov-file#textfile-collector).

Open the `docker-compose.yml` of the metrics stack and update the `node-exporter` service with a new volume mount and matching command argument:

```yml
services:
  exporter:
    image: quay.io/prometheus/node-exporter
    ...
    volumes:
      - ...
      - /data/app-borgmatic/data/borgmatic-exporter/metrics:/data/borgmatic-metrics:ro
    command:
      - "--collector.textfile.directory=/data/borgmatic-metrics"
```

Next, restart the exporter service:

``` bash
docker compose up -d exporter
```

The Borgmatic metrics will now be collected my Prometheus and will be available for visualization in Grafana.

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

### Run commands inside a container

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
### External links
- [https://torsion.org/borgmatic/](https://torsion.org/borgmatic/)
- [https://github.com/borgmatic-collective/docker-borgmatic](https://github.com/borgmatic-collective/docker-borgmatic)
- [https://github.com/maxim-mityutko/borgmatic-exporter](https://github.com/maxim-mityutko/borgmatic-exporter)

## Discussions

### Per-app configuration

It is possible to use multiple configuration files with different configuration values, to backup different parts of the server with a different backup policy.
This is for example useful to apply different retentions for logs and backup dumps.

To use this, just add several `.yml` files inside `./config/borgmatic.d/`.
Each invocation of `borgmatic` will apply these files independently, in sequence.
