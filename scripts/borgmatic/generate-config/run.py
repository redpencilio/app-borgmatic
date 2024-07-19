#!/usr/bin/env python3

"""Generate a sample borgmatic configuration based on user's answers."""

import os
import random
import subprocess


def main() -> None:
    """Generate config based on user input"""

    print("Generating a Borgmatic configuration:")
    print("***")

    local_hostname = get_local_hostname()
    repo_name = get_repo_name()

    backup_server_host = get_backup_server_host()
    backup_server_port = get_backup_server_port()
    backup_server_user = get_backup_server_user()
    backup_server_string = f"ssh://{backup_server_user}@{backup_server_host}:{backup_server_port}/./{local_hostname}-{repo_name}.borg"

    passphrase = get_passphrase()
    ssh_key_path = get_ssh_key_path()
    # TODO: this works, uncomment: (it's just not usefull for testing)
    # authorize_ssh_key_on_backup_server(
    #     ssh_key_path, backup_server_user, backup_server_host, backup_server_port
    # )

    app_names: list = get_app_names()


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


def get_local_hostname() -> str:
    """Try to find local hostname and ask the user to confirm"""

    cmd = subprocess.run(["hostname"], capture_output=True, check=True)
    local_hostname = cmd.stdout.decode().strip()

    local_hostname = ask_user("Hostname of the server to backup", local_hostname)

    return local_hostname


def get_repo_name() -> str:
    """Ask what name the repo should be given"""

    repo_name = ask_user("Name to be given to the repo", "main")

    return repo_name


def get_backup_server_host() -> str:
    """Ask for the name of the backup server"""

    return ask_user("Hostname of the backup server (can also be an IP address)", "")


def get_backup_server_port() -> str:
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


def get_backup_server_user() -> str:
    """Ask for the backup server's connection user"""

    return ask_user("Username for the backup server", "root")


def get_passphrase() -> str:
    """Ask for a passphrase or generate one"""

    passphrase = ask_user("Passphrase for the repo (leave empty to generate)", "")
    if not passphrase:
        population = (
            "0123456789" "abcdefghijklmnopqrstuvwxyz" "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )
        passphrase = "".join(random.choices(population, k=64))

    return passphrase


def get_ssh_key_path() -> str:
    """Ask for the path to an SSH key and generate if non existant"""

    ssh_key_path = ask_user("Path to SSH key for the backups", "~/.ssh/id_borgmatic")
    ssh_key_path = os.path.expanduser(ssh_key_path)
    ssh_key_path = ssh_key_path.rstrip(".pub")

    if not os.path.exists(ssh_key_path):
        print(f"{ssh_key_path} was not found. Generating a key for you")
        subprocess.run(
            ["ssh-keygen", "-f", ssh_key_path, "-N", ""],
            check=True,
        )

    return ssh_key_path


def authorize_ssh_key_on_backup_server(ssh_key_path, user, host, port) -> None:
    """Add authorized_keys line to backup server with our SSH key and some options"""

    if not ssh_key_path.endswith(".pub"):
        ssh_key_path += ".pub"

    restrict_line = 'command="borg serve --umask=077 --info",restrict'

    sftp_script = (
        "mkdir .ssh\n"
        "touch -ac .ssh/authorized_keys\n"
        "get .ssh/authorized_keys /tmp/authorized_keys\n"
        f'!grep -q "$(cat {ssh_key_path})" /tmp/authorized_keys'
        f" || echo '{restrict_line}' $(cat {ssh_key_path}) >> /tmp/authorized_keys\n"
        "put /tmp/authorized_keys .ssh/authorized_keys\n"
        "!rm /tmp/authorized_keys\n"
        "bye\n"
    )

    subprocess.run(
        [
            "sftp",
            "-P",
            port,
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{user}@{host}",
        ],
        input=sftp_script.encode(),
        check=True,
    )


def get_app_names() -> list:
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


if __name__ == "__main__":
    main()
