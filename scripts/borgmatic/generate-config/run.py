#!/usr/bin/env python3

"""Generate a sample borgmatic configuration based on user's answers."""

import subprocess


def main() -> None:
    """Generate config based on user input"""

    print("Generating a Borgmatic configuration:")
    print("***")

    local_hostname = get_local_hostname()

    repo_name = get_repo_name()

    backup_server_string = get_backup_server_string(local_hostname, repo_name)
    print(backup_server_string)

    app_names: list = get_app_names()
    print(app_names)


def get_local_hostname() -> str:
    """Try to find local hostname and ask the user to confirm"""

    cmd = subprocess.run("hostname", capture_output=True, check=True)
    local_hostname = cmd.stdout.decode().strip()

    user_hostname = input(f"Hostname of the server to backup [{local_hostname}]: ")
    if user_hostname:
        local_hostname = user_hostname

    return local_hostname


def get_repo_name() -> str:
    """Ask what name the repo should be given"""

    repo_name = input("Name to be given to the repo [main]: ")
    if not repo_name:
        repo_name = "main"

    return repo_name


def get_backup_server_string(local_hostname: str, repo_name: str) -> str:
    """Ask what's needed to build the backup server string"""

    print("Hostname of the backup server:")
    print("  This can also be an IP address")
    hostname = input()

    port = -1
    while port == -1:
        port = input("SSH port of the backup server [23]: ")
        if not port:
            port = "23"
        try:
            port = int(port)
        except ValueError:
            print(f"  not a valid port: {port}")
            port = -1

    username = input("Username for the backup server [root]: ")
    if not username:
        username = "root"

    return f"ssh://{username}@{hostname}:{port}/./{local_hostname}-{repo_name}.borg"


def get_app_names() -> list:
    """Ask for a list of apps to backup"""

    print("Name(s) of app(s) to backup:")
    print(
        '  If multiple, separate them with whitespace (e.g. "app-rollvolet-crm app-server-monitor")'
    )
    app_names = input()

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

    print("Should I randomly generate passphrase? (y/n)")
    print("What's the crontab pattern for app backup ?")


if __name__ == "__main__":
    main()
