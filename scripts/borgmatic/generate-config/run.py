#!/usr/bin/env python3

"""Generate a sample borgmatic configuration based on user's answers."""

import os
import random
import subprocess


def main() -> None:
    """Generate config based on user input"""

    config_generator = ConfigGenerator()


class ConfigGenerator:
    """Class to build a Borgmatic configuration"""

    def __init__(self):
        print("Generating a Borgmatic configuration:")
        print("***")
        self.local_hostname = self.get_local_hostname()
        self.repo_name = self.get_repo_name()
        self.append_only = self.is_append_only()
        self.backup_server_host = self.get_backup_server_host()
        self.backup_server_port = self.get_backup_server_port()
        self.backup_server_user = self.get_backup_server_user()
        self.backup_server_string = f"ssh://{self.backup_server_user}@{self.backup_server_host}:{self.backup_server_port}/./{self.local_hostname}-{self.repo_name}.borg"
        self.passphrase = self.get_passphrase()
        self.ssh_key_path = self.get_ssh_key_path()
        self.authorize_ssh_key_on_backup_server()
        self.app_names = self.get_app_names()

    def get_local_hostname(self) -> str:
        """Try to find local hostname and ask the user to confirm"""

        cmd = subprocess.run(["hostname"], capture_output=True, check=True)
        local_hostname = cmd.stdout.decode().strip()

        local_hostname = ask_user("Hostname of the server to backup", local_hostname)

        return local_hostname

    def get_repo_name(self) -> str:
        """Ask what name the repo should be given"""

        repo_name = ask_user("Name to be given to the repo", "main")

        return repo_name

    def is_append_only(self) -> bool:
        """Ask if we should configure append_only mode"""

        user_answer = ask_user("Should the repo be append-only?", "Yn")
        if user_answer == "n":
            return False
        return True

    def get_backup_server_host(self) -> str:
        """Ask for the name of the backup server"""

        return ask_user("Hostname of the backup server (can also be an IP address)", "")

    def get_backup_server_port(self) -> str:
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

        return port

    def get_backup_server_user(self) -> str:
        """Ask for the backup server's connection user"""

        return ask_user("Username for the backup server", "root")

    def get_passphrase(self) -> str:
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

        return passphrase

    def get_ssh_key_path(self) -> str:
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
            )

        return ssh_key_path

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

    def get_app_names(self) -> list:
        """Ask for a list of apps to backup"""

        app_names = ask_user(
            "Name(s) of app(s) to backup\n"
            "  If multiple, separate them with whitespace "
            '(e.g. "app-rollvolet-crm app-server-monitor")',
            "",
        )

        return [app.strip() for app in app_names.split()]


def todo():
    print(
        "Does the app contain a triplestore?  (y/n)"
        "=> if yes, add data/db folder to backup dirs and backup Virtuoso in before hook"
    )
    print(
        "Does the app contain mu-search? => if yes, add data/elasticsearch to backup dirs"
    )
    print(
        "Does the app contain a file service => if yes, add data/files to backup dirs"
    )

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
