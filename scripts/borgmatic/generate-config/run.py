#!/usr/bin/env python3

"""Generate a sample borgmatic configuration based on user's answers."""

import os
import random
import re
import subprocess


def main() -> None:
    """Generate config based on user input"""

    config_generator = ConfigGenerator()
    config_generator.write_config()


class ConfigGenerator:
    """Class to build a Borgmatic configuration"""

    def __init__(self):
        print("Generating a Borgmatic configuration:")
        print("***")
        self.work_dir = "/data/app"
        self.get_hostname()
        self.get_repo_name()
        self.get_append_only()
        self.get_backup_server_host()
        self.get_backup_server_port()
        self.get_backup_server_user()
        self.get_backup_server_string()
        self.get_passphrase()
        self.get_ssh_key_path()
        self.authorize_ssh_key_on_backup_server()
        self.get_app_names()

    def get_hostname(self) -> None:
        """Try to find the hostname and ask the user to confirm"""

        cmd = subprocess.run(["hostname"], capture_output=True, check=True)
        hostname = cmd.stdout.decode().strip()

        self.hostname = ask_user("Hostname of the server to backup", hostname)

    def get_repo_name(self) -> None:
        """Ask what name the repo should be given"""

        self.repo_name = ask_user("Name to be given to the repo", "main")

    def get_append_only(self) -> None:
        """Ask if we should configure append_only mode"""

        user_answer = ask_user("Should the repo be append-only?", "Yn")
        if user_answer == "n":
            self.append_only = False
        else:
            self.append_only = True

    def get_backup_server_host(self) -> None:
        """Ask for the name of the backup server"""

        self.backup_server_host = ask_user(
            "Hostname of the backup server (can also be an IP address)", ""
        )

    def get_backup_server_port(self) -> None:
        """Ask for the backup server's SSH port"""

        ok_port = False
        while not ok_port:
            port = ask_user("SSH port of the backup server", "23")
            try:
                int(port)
            except ValueError:
                print(f"Not a valid port: {port}")
            else:
                if 0 < int(port) < 65535:
                    ok_port = True

        self.backup_server_port = port

    def get_backup_server_user(self) -> None:
        """Ask for the backup server's connection user"""

        self.backup_server_user = ask_user("Username for the backup server", "root")

    def get_backup_server_string(self) -> None:
        """Build the string for connecting to the backup server"""

        self.backup_server_string = f"ssh://{self.backup_server_user}@{self.backup_server_host}:{self.backup_server_port}/./{self.hostname}-{self.repo_name}.borg"

    def get_passphrase(self) -> None:
        """Ask for a passphrase or generate one"""

        passphrase = ask_user("Passphrase for the repo (leave empty to generate)", "")
        if not passphrase:
            population = "".join(
                (
                    "".join(str(i) for i in range(10)),
                    "".join(chr(i) for i in range(ord("a"), ord("z") + 1)),
                    "".join(chr(i) for i in range(ord("A"), ord("Z") + 1)),
                )
            )
            passphrase = "".join(random.choices(population, k=64))

        self.passphrase = passphrase

    def get_ssh_key_path(self) -> None:
        """Ask for the path to an SSH key and generate if non existant"""

        ssh_key_path = ask_user(
            "Path to SSH key for the backups", "~/.ssh/id_borgmatic"
        )
        ssh_key_path = os.path.expanduser(ssh_key_path)
        ssh_key_path = ssh_key_path.rstrip(".pub")

        if not os.path.exists(ssh_key_path):
            print(f"{ssh_key_path} was not found. Generating a key for you")
            subprocess.run(
                ["ssh-keygen", "-f", ssh_key_path, "-N", ""],
                check=True,
                capture_output=True,
            )

        self.ssh_key_path = ssh_key_path

    def authorize_ssh_key_on_backup_server(self) -> None:
        """Add authorized_keys line to backup server with our SSH key and some options"""

        return  # TODO: remove (this works, it's just not usefull for testing)

        ssh_key_path = self.ssh_key_path
        if not ssh_key_path.endswith(".pub"):
            ssh_key_path += ".pub"

        if self.append_only:
            restrict_line = (
                'command="borg serve --umask=077 --info --append_only",restrict'
            )
        else:
            restrict_line = 'command="borg serve --umask=077 --info",restrict'

        sftp_script = f"""
            mkdir .ssh
            touch -ac .ssh/authorized_keys
            get .ssh/authorized_keys /tmp/authorized_keys
            !grep -q "$(cat {ssh_key_path})" /tmp/authorized_keys || echo '{restrict_line}' $(cat {ssh_key_path}) >> /tmp/authorized_keys
            put /tmp/authorized_keys .ssh/authorized_keys
            !rm /tmp/authorized_keys
            bye
        """

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
        )

    def get_app_names(self) -> None:
        """Ask for a list of apps to backup"""

        app_names = ask_user(
            "Name(s) of app(s) to backup\n"
            "  If multiple, separate them with whitespace "
            '(e.g. "app-rollvolet-crm app-server-monitor")',
            "",
        )

        self.app_names = [app.strip() for app in app_names.split()]
        self.source_directories = []
        self.before_hooks = []

        for app_name in self.app_names:
            # triplestore
            user_answer = ask_user(f"Does {app_name} contain a triplestore?", "yN")
            if user_answer == "y":
                source_dir = os.path.join("/data", app_name, "data/db")
                print(f"Adding {source_dir} to source_directories")
                self.source_directories.append(source_dir)
                print("Adding virtuoso backup hook")
                self.before_hooks.append(
                    "/data/useful-scripts/virtuoso-backup.sh $(/usr/bin/docker ps "
                    f'--filter "label=com.docker.compose.project={app_name}" '
                    '--filter "label=com.docker.compose.service=triplestore" '
                    '--format "{{.Names}}")'
                )

            # mu-search
            user_answer = ask_user(f"Does {app_name} contain mu-search?", "yN")
            if user_answer == "y":
                source_dir = os.path.join("/data", app_name, "data/elasticsearch")
                print(f"Adding {source_dir} to source_directories")
                self.source_directories.append(source_dir)

            # file service
            user_answer = ask_user(f"Does {app_name} contain a file service?", "yN")
            if user_answer == "y":
                source_dir = os.path.join("/data", app_name, "data/files")
                print(f"Adding {source_dir} to source_directories")
                self.source_directories.append(source_dir)

    def write_config(self) -> None:
        """Write the configuration"""

        destination_file = os.path.join(
            self.work_dir, "config/borgmatic.d", f"{self.repo_name}.yaml"
        )
        example_conf_file = os.path.join(self.work_dir, "config.example.yaml")
        with open(example_conf_file, "r", encoding="utf-8") as example_config:
            config_content = example_config.read()

        config_content = re.sub(
            r"^archive_name_format:.*",
            f"archive_name_format: '{self.hostname}-{self.repo_name}-{{now}}'",
            config_content,
            flags=re.MULTILINE,
        )
        config_content = re.sub(
            r"^repositories:\n\s+- path: .*\n\s+  label: .*",
            "repositories:\n"
            f'    - path: "{self.backup_server_string}"\n'
            f"      label: {self.repo_name}",
            config_content,
            flags=re.MULTILINE,
        )
        config_content = re.sub(
            r"^encryption_passphrase:.*",
            f'encryption_passphrase: "{self.passphrase}"',
            config_content,
            flags=re.MULTILINE,
        )
        config_content = re.sub(
            r"^ssh_command:.*",
            f"ssh_command: ssh -i {self.ssh_key_path}",
            config_content,
            flags=re.MULTILINE,
        )
        config_content = re.sub(
            r"^source_directories:\n(?:^ +.+\n)+",
            "source_directories:\n"
            "    - " + "\n    - ".join(dir for dir in self.source_directories) + "\n",
            config_content,
            flags=re.MULTILINE,
        )
        if self.before_hooks:
            config_content = re.sub(
                r"^#? ?before_backup:\n(?:^ +.+\n)+",
                "before_backup:\n"
                "    - " + "\n    - ".join(hook for hook in self.before_hooks) + "\n",
                config_content,
                flags=re.MULTILINE,
            )
        if self.append_only:
            config_content = re.sub(
                r"^#? ?skip_actions:\n(?:^ +.+\n)+",
                "skip_actions:\n"
                "    - compact\n"
                "    - prune\n",
                config_content,
                flags=re.MULTILINE,
            )
            config_content = re.sub(
                r"^#? ?keep_.+\n?",
                "",
                config_content,
                flags=re.MULTILINE,
            )

        # We are done, remove comments to have a cleaner file
        config_content = re.sub(
            r"^ *#.*\n?",
            "",
            config_content,
            flags=re.MULTILINE,
        )

        with open(destination_file, "w", encoding="utf-8") as dest_config:
            dest_config.write(config_content)
        os.chmod(destination_file, 0o600)

        print(f"Created {destination_file.lstrip(self.work_dir)}.")
        print("Please review it before starting containers.")


def todo():

    print("What's the crontab pattern for app backup ?")


def ask_user(question: str, default: str) -> str:
    """Ask for user input and return the answer"""

    print(question)

    if default:
        answer = input(f"[{default}] ")
    else:
        answer = input()

    if not answer:
        answer = default

    return answer


if __name__ == "__main__":
    main()
