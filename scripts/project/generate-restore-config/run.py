#!/usr/bin/env python3
import sys
import os
import re
import inspect
from pathlib import Path

def main() -> None:
  _, repository_path, passphrase = sys.argv
  work_dir = "/project"
  match = re.search(r'/\./(.*)\.borg', repository_path)
  repository_name = match.group(1) if match else 'app'

  print(f"\nGenerating config to restore {repository_name}")
  generate_borgmatic_config(repository_path, repository_name, passphrase, work_dir)
  print_post_script_documentation(repository_name)

def generate_borgmatic_config(repository_path, repository_name, passphrase, work_dir) -> None:
  """Generate borgmatic configuration file to connect to a backup server"""
  config_file_path = os.path.join(work_dir, "config/borgmatic.d", f"{repository_name}.yml")
  config_content = inspect.cleandoc(
    f"""
    match_archives: sh:*

    repositories:
        - path: "{repository_path}"
          label: {repository_name}

    encryption_passphrase: "{passphrase}"
    """)

  ssh_work_dir_key_path = os.path.join(work_dir, "ssh-keys", "id_borgmatic")
  ssh_container_key_path = "/root/.ssh/id_borgmatic"
  if os.path.exists(ssh_work_dir_key_path):
    config_content += f"\nssh_command: ssh -i {ssh_container_key_path}"
  else:
    print(f"\nNo SSH key found in .{ssh_work_dir_key_path[len(work_dir):]}.\nRestore will be configured to use password authentication which may be cumbersome since you'll have to enter the password multiple times.\nIf you want to authenticate with an SSH key, provide one in .{ssh_work_dir_key_path[len(work_dir):]} and rerun the script.\n")

  print(f"Creating Borgmatic config file at .{config_file_path[len(work_dir):]}")
  with open(config_file_path, "w", encoding="utf-8") as file:
    file.write(config_content)
  os.chmod(config_file_path, 0o600)

def print_post_script_documentation(repository_name):
  print("\nYour app is almost ready to restore!")
  print("Execute the following steps to finish the setup:")
  print("> drc up -d (or 'drc restart borgmatic-restore' if your stack is already running)")

  print("\nList the available backups:")
  print(f"> drc exec borgmatic-restore borgmatic list --repository {repository_name}")

if __name__ == '__main__':
  if len(sys.argv) < 2: # sys.argv[0] is the script name. Arguments start at index 1.
    print(f"\nScript expects 2 args, only {len(sys.argv) - 1} were passed.")
    print(f"- repository_path: complete SSH connection string to the backup repository (e.g. ssh://u1234-sub1@u1234.your-storagebox.de:23/./abb-croco-app-mandatendatabank.borg)")
    print(f"- passphrase: secret passphrase of the backup repository")
    sys.exit(1)
  else:
    main()
