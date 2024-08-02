#!/usr/bin/env python3

"""Generate a sample borgmatic configuration based on user's answers."""

import inspect
import os
import random
import subprocess


def main() -> None:
    """Generate config based on user input"""

    config_generator = ConfigGenerator()
    for app_name in config_generator.apps:
        config_generator.write_config(app_name)
    config_generator.write_docker_compose_override()
    config_generator.print_remaining_tasks()


class ConfigGenerator:
    """Class to build a Borgmatic configuration"""

    def __init__(self):
        print("Generating a Borgmatic configuration:")
        self.work_dir = "/data/app"
        self.repo_dir = "."
        self.set_backup_server_host()
        self.set_backup_server_port()
        self.set_backup_server_user()
        self.set_hostname()
        if ask_user("Authorize SSH key on backup server?", "yN") == "y":
            self.authorize_ssh_key_on_backup_server()

        self.set_app_names()
        self.set_backup_server_strings()
        self.set_passphrases()
        self.set_app_attributes()

    def set_app_names(self) -> None:
        """Ask for a list of apps to backup, a separate config will be made for each"""

        app_names = ask_user(
            "Name(s) of app(s) to backup "
            "(if multiple, separate them with whitespace):",
            "app-rollvolet-crm app-server-monitor",
        )
        self.apps = {
            app_name.strip(): {
                "passphrase": "",
                "backup_server_string": "",
                "source_directories": set(),
                "before_hooks": set(),
                "after_hooks": set(),
                "docker_mounts": set(),
            }
            for app_name in app_names.split()
        }

    def set_hostname(self) -> None:
        """Try to find the hostname and ask the user to confirm"""

        cmd = subprocess.run(["hostname"], capture_output=True, check=True)
        hostname = cmd.stdout.decode().strip()

        self.hostname = ask_user("Hostname of the server to backup:", hostname)

    def set_backup_server_host(self) -> None:
        """Ask for the name of the backup server"""

        self.backup_server_host = ask_user(
            "Hostname of the backup server (can also be an IP address):",
            "u339567.your-storagebox.de",
        )

    def set_backup_server_port(self) -> None:
        """Ask for the backup server's SSH port"""

        ok_port = False
        while not ok_port:
            port = ask_user("SSH port of the backup server:", "23")
            try:
                int(port)
            except ValueError:
                print(f"Not a valid port: {port}")
            else:
                if 0 < int(port) < 65535:
                    ok_port = True

        self.backup_server_port = port

    def set_backup_server_user(self) -> None:
        """Ask for the backup server's connection user"""

        self.backup_server_user = ask_user(
            "Username for the backup server:",
            "u339567-sub1",
        )

    def set_backup_server_strings(self) -> None:
        """Build the string for connecting to the backup server"""

        for app_name in self.apps:
            self.apps[app_name]["backup_server_string"] = f"ssh://{self.backup_server_user}@{self.backup_server_host}:{self.backup_server_port}/./{self.hostname}-{app_name}.borg"

    def set_passphrases(self) -> None:
        """Ask for a passphrase or generate one"""

        population = "".join(
            (
                "".join(str(i) for i in range(10)),
                "".join(chr(i) for i in range(ord("a"), ord("z") + 1)),
                "".join(chr(i) for i in range(ord("A"), ord("Z") + 1)),
            )
        )

        for app_name in self.apps:
            print(f"\nGenerating passphrase for {app_name}...")
            self.apps[app_name]["passphrase"] = "".join(
                random.choices(population, k=64)
            )

    def _set_ssh_key_pub(self) -> None:
        """Ask for the content of a public SSH key or generate one"""

        ssh_key_path = os.path.join(self.work_dir, "id_borgmatic")

        self.ssh_key_pub = ask_user(
            "Content of an existing public SSH key for the backups (leave empty to generate):", ""
        )
        if not self.ssh_key_pub:
            if not os.path.exists(ssh_key_path):
                print(f"Generating new key at {self.repo_dir}/id_borgmatic...")
                subprocess.run(
                    ["ssh-keygen", "-f", ssh_key_path, "-N", ""],
                    check=True,
                    capture_output=True,
                )
            else:
                print(f"Found existing key at {self.repo_dir}/id_borgmatic, using it.")
            with open(f"{ssh_key_path}.pub", "r", encoding="utf-8") as ssh_key_file:
                self.ssh_key_pub = ssh_key_file.read()
        self.ssh_key_pub = self.ssh_key_pub.strip()

    def authorize_ssh_key_on_backup_server(self) -> None:
        """Add authorized_keys line to backup server with our SSH key and some options"""

        self._set_ssh_key_pub()

        restrict_line = 'command="borg serve --umask=077 --info --append_only",restrict'

        sftp_script = inspect.cleandoc(
            f"""
            mkdir .ssh
            touch -ac .ssh/authorized_keys
            get .ssh/authorized_keys /tmp/authorized_keys
            !grep -q "{self.ssh_key_pub}" /tmp/authorized_keys || echo '{restrict_line}' {self.ssh_key_pub} >> /tmp/authorized_keys
            put /tmp/authorized_keys .ssh/authorized_keys
            !rm /tmp/authorized_keys
            bye
            """
        )

        subprocess.run(
            [
                "sftp",
                "-P",
                self.backup_server_port,
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"{self.backup_server_user}@{self.backup_server_host}",
            ],
            input=sftp_script.encode(),
            check=True,
            capture_output=True,
        )

    def set_app_attributes(self) -> None:
        """For each app_name set attributes for the app"""

        for app_name in self.apps:
            # app's docker-compose files
            self.apps[app_name]["source_directories"].add(
                f"/data/{app_name}/docker-compose*.yml"
            )
            self.apps[app_name]["docker_mounts"].add(
                f"/data/{app_name}:/data/{app_name}:ro"
            )

            # app's config directory
            self.apps[app_name]["source_directories"].add(f"/data/{app_name}/config")
            self.apps[app_name]["docker_mounts"].add(
                f"/data/{app_name}/config:/data/{app_name}/config:ro"
            )

            # triplestore
            user_answer = ask_user(f"Does {app_name} contain a triplestore?", "Yn")
            if user_answer.lower() in ("yn", "y", "yes", "1"):
                self.apps[app_name]["source_directories"].add(
                    f"/data/{app_name}/data/db"
                )
                self.apps[app_name]["before_hooks"].add(
                    "/data/useful-scripts/virtuoso-backup.sh $(/usr/bin/docker ps "
                    f'--filter "label=com.docker.compose.project={app_name}" '
                    '--filter "label=com.docker.compose.service=triplestore" '
                    '--format "{{.Names}}")'
                )
                self.apps[app_name]["after_hooks"].add(
                    f"find /data/{app_name}/data/db/backups -type f -delete"
                )
                self.apps[app_name]["docker_mounts"].add(
                    "/data/useful-scripts:/data/useful-scripts:ro"
                )
                self.apps[app_name]["docker_mounts"].add(
                    f"/data/{app_name}/data/db:/data/{app_name}/data/db:ro"
                )
                # backups subdir not readonly for cleanup in after_backup hook
                self.apps[app_name]["docker_mounts"].add(
                    f"/data/{app_name}/data/db/backups:/data/{app_name}/data/db/backups"
                )

            # mu-search
            user_answer = ask_user(f"Does {app_name} contain mu-search?", "yN")
            if user_answer == "y":
                self.apps[app_name]["source_directories"].add(
                    f"/data/{app_name}/data/elasticsearch"
                )
                self.apps[app_name]["docker_mounts"].add(
                    f"/data/{app_name}/data/elasticsearch:/data/{app_name}/data/elasticsearch:ro"
                )

            # file service
            user_answer = ask_user(f"Does {app_name} contain a file service?", "yN")
            if user_answer == "y":
                self.apps[app_name]["source_directories"].add(
                    f"/data/{app_name}/data/files"
                )
                self.apps[app_name]["docker_mounts"].add(
                    f"/data/{app_name}/data/files:/data/{app_name}/data/files:ro"
                )

    def write_config(self, app_name: str) -> None:
        """Write the configuration"""

        destination_file = os.path.join(
            self.work_dir, "config/borgmatic.d", f"{app_name}.yml"
        )

        config_content = inspect.cleandoc(
            f"""
            # Generated with `generate-config` script

            archive_name_format: '{self.hostname}-{app_name}-{{now}}'

            repositories:
                - path: "{self.apps[app_name]['backup_server_string']}"
                  label: {app_name}

            encryption_passphrase: "{self.apps[app_name]['passphrase']}"

            ssh_command: ssh -i /root/.ssh/id_borgmatic
            """
        )

        config_content += (
            "\n\n"
            "source_directories:\n"
            "    - " + "\n    - ".join(
                dir for dir in sorted(self.apps[app_name]["source_directories"])
            )
        )

        if self.apps[app_name]["before_hooks"]:
            config_content += (
                "\n\n"
                "before_backup:\n"
                "    - " + "\n    - ".join(
                    hook for hook in self.apps[app_name]["before_hooks"]
                )
            )

        if self.apps[app_name]["after_hooks"]:
            config_content += (
                "\n\n"
                "after_backup:\n"
                "    - " + "\n    - ".join(
                    hook for hook in self.apps[app_name]["after_hooks"]
                )
            )

        config_content += (
            "\n\n"
            "skip_actions:\n"
            "    - compact\n"
            "    - prune\n"
        )

        if not config_content.endswith("\n"):
            config_content += "\n"
        with open(destination_file, "w", encoding="utf-8") as dest_file:
            dest_file.write(config_content)
        os.chmod(destination_file, 0o600)

        print(f"Created configuration at {destination_file.lstrip(self.work_dir)}.")

    def write_docker_compose_override(self) -> None:
        """Write the docker-compose.override.yml"""

        destination_file = os.path.join(self.work_dir, "docker-compose.override.yml")

        docker_compose_content = inspect.cleandoc(
            """
            # Generated with `generate-config` script

            version: '3'

            services:
              borgmatic:
            """
        )

        docker_mounts = set()
        for app_name in self.apps:
            docker_mounts = docker_mounts.union(self.apps[app_name]["docker_mounts"])

        docker_compose_content += (
            "\n"
            "    volumes:\n"
            "      - " + "\n      - ".join(
                mount for mount in sorted(docker_mounts)
            )
        )

        existing_configs = [
            file for file in os.listdir(f"{self.work_dir}/config/borgmatic.d")
            if file.endswith(".yaml") or file.endswith(".yml")
        ]

        docker_compose_content += (
            "\n"
            "  borgmatic-exporter:\n"
            "    environment:\n"
            '      BORGMATIC_CONFIG: "' + ":".join(
                f"/etc/borgmatic.d/{config}" for config in existing_configs
            ) + '"'
        )

        if not docker_compose_content.endswith("\n"):
            docker_compose_content += "\n"
        with open(destination_file, "w", encoding="utf-8") as dest_file:
            dest_file.write(docker_compose_content)

    def print_remaining_tasks(self) -> None:
        """Some manual tasks are needed, print them here"""

        print()
        print(inspect.cleandoc(
            f"""
            A configuration file and docker-compose.override.yml were written.
            You might want to:
              - Review the configuration files
              - Check that the SSH key exists (by default at /root/.ssh/id_borgmatic).
                If the script generated one, make sure to move it (from {self.repo_dir}/id_borgmatic).
              - Check the BORGMATIC_CONFIG variable lists all borgmatic configuration files:
                `docker compose config | grep BORGMATIC_CONFIG`
              - Verify the cron patterns for borgmatic and borgmatic-exporter:
                `docker compose config | grep CRON`
              - This script sets the repo in append-only mode. If you don't want that, you'll need to
                make the relevant changes yourself.

            If everything is OK, you can start the containers and initialize the repository:
              `docker compose up -d`
              `docker compose exec borgmatic borgmatic init -e repokey --append-only`

            As a precaution you might want to export the encryption key:
              `docker compose exec borgmatic borgmatic key export`
            """
        ))


def ask_user(question: str, default: str) -> str:
    """Ask for user input and return the answer"""

    print(f"\n{question}")

    if default:
        answer = input(f"[{default}] ")
    else:
        answer = input()

    if not answer:
        answer = default

    return answer


if __name__ == "__main__":
    main()
