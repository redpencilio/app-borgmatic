#!/usr/bin/env python3
import sys
import os
import re
import random
import inspect
import yaml
from pathlib import Path

def main() -> None:
  type, ssh_connection_string, hostname, app_name = validate_arguments(sys.argv)
  work_dir = "/project"
  print(f"\nGenerating config to backup {app_name}")
  passphrase = generate_passphrase()
  generate_borgmatic_config(type, ssh_connection_string, hostname, app_name, passphrase, work_dir)
  update_docker_compose_override(type, app_name, work_dir)
  print_post_script_documentation(app_name)

def validate_arguments(sys_args) -> [str]:
  _, type, ssh_connection_string, hostname, app_name = sys_args

  if type not in ["app", "http-log"]:
    print("Argument 'type' must be one of 'app' or 'http-log'")
    sys.exit(1)

  ssh_connection_pattern = r':(\d*)$'
  if re.search(ssh_connection_pattern, ssh_connection_string):
    valid_ssh_connection_string = ssh_connection_string
  else:
    valid_ssh_connection_string = ssh_connection_string + ":"

  return [type, valid_ssh_connection_string, hostname, app_name]

def generate_passphrase() -> str:
  population = "".join(
    (
      "".join(str(i) for i in range(10)),
      "".join(chr(i) for i in range(ord("a"), ord("z") + 1)),
      "".join(chr(i) for i in range(ord("A"), ord("Z") + 1)),
    )
  )
  passphrase = "".join(random.choices(population, k=64))
  print("Generating passphrase...")
  print("#########################################################################")
  print("                              Passphrase:                                ")
  print(f"    {passphrase}")
  print("#########################################################################")
  return passphrase

def generate_borgmatic_config(type, ssh_connection_string, hostname, app_name, passphrase, work_dir) -> None:
  """Generate borgmatic configuration file for backup of a semantic.works application stack"""
  config_file_path = os.path.join(work_dir, "config/borgmatic.d", f"{app_name}.yml")

  if type == "app":
    config_content = borgmatic_config_for_semantic_works_app(ssh_connection_string, hostname, app_name, passphrase)
  else:
    config_content = borgmatic_config_for_http_logs(ssh_connection_string, hostname, app_name, passphrase)

  print(f"Creating Borgmatic config file at .{config_file_path[len(work_dir):]}")
  with open(config_file_path, "w", encoding="utf-8") as file:
    file.write(config_content)
  os.chmod(config_file_path, 0o600)

def borgmatic_config_for_semantic_works_app(ssh_connection_string, hostname, app_name, passphrase) -> str:
  return inspect.cleandoc(
    f"""
    archive_name_format: '{hostname}-{app_name}-{{now}}'

    repositories:
        - path: "ssh://{ssh_connection_string}/./{hostname}-{app_name}.borg"
          label: {app_name}

    encryption_passphrase: "{passphrase}"
    ssh_command: ssh -i /root/.ssh/id_borgmatic

    source_directories:
        - /data/{app_name}/docker-compose*.yml
        - /data/{app_name}/config
        - /data/{app_name}/data/db
        - /data/{app_name}/data/authorization
        - /data/{app_name}/data/elasticsearch
        - /data/{app_name}/data/files

    before_backup:
        - /data/useful-scripts/virtuoso-backup.sh $(/usr/bin/docker ps --filter "label=com.docker.compose.project={app_name}" --filter "label=com.docker.compose.service=triplestore" --format "{{.Names}}")

    after_backup:
        - find /data/{app_name}/data/db/backups -type f -delete

    skip_actions:
        - compact
        - prune
    """
  )

def borgmatic_config_for_http_logs(ssh_connection_string, hostname, app_name, passphrase) -> str:
  return inspect.cleandoc(
    f"""
    archive_name_format: '{hostname}-{app_name}-{{now}}'

    repositories:
        - path: "ssh://{ssh_connection_string}/./{hostname}-{app_name}.borg"
          label: {app_name}

    encryption_passphrase: "{passphrase}"
    ssh_command: ssh -i /root/.ssh/id_borgmatic

    source_directories:
        - /data/{app_name}/data/compressed/*/*.tar.gz
        - /data/{app_name}/data/encrypted/*/*.gpg

    after_backup:
        - find /data/{app_name}/data/compressed -type f -name "*.tar.gz" -delete
        - find /data/{app_name}/data/encrypted -type f -name "*.gpg" -delete

    skip_actions:
        - compact
        - prune
    """
  )

def update_docker_compose_override(type, app_name, work_dir) -> None:
  """Update the mounted volumes in the docker-compose.override.yml"""

  # Parse docker-compose.override.yml
  print("Updating docker-compose.override.yml")
  docker_compose_path = os.path.join(work_dir, "docker-compose.override.yml")
  Path(docker_compose_path).touch(exist_ok=True)
  with open(docker_compose_path, "r", encoding="utf-8") as file:
    docker_compose = yaml.safe_load(file) or {}

  print("- Update mounted volumes of borgmatic service")
  services = docker_compose.setdefault("services", {})
  borgmatic_service = services.setdefault("borgmatic", {})
  borgmatic_service_volumes = borgmatic_service.setdefault("volumes", [])
  new_volumes = ["/data/useful-scripts:/data/useful-scripts:ro"]
  if type == "app":
    new_volumes.extend([
      f"/data/{app_name}:/data/{app_name}:ro",
      f"/data/{app_name}/data/db/backups:/data/{app_name}/data/db/backups"
    ])
  else:
    new_volumes.extend([
      f"/data/{app_name}/data/compressed:/data/{app_name}/data/compressed",
      f"/data/{app_name}/data/encrypted:/data/{app_name}/data/encrypted"
    ])
  for volume in new_volumes:
    if volume not in borgmatic_service_volumes:
      borgmatic_service_volumes.append(volume)

  print("- Update BORGMATIC_CONFIG env var of borgmatic-exporter service")
  exporter_service = services.setdefault("borgmatic-exporter", {})
  exporter_service_env_vars = exporter_service.setdefault("environment", {})
  borgmatic_config_env_var = exporter_service_env_vars.setdefault("BORGMATIC_CONFIG", "")
  borgmatic_config_files = [file for file in borgmatic_config_env_var.split(":") if file.strip()]
  new_config_file = f"/etc/borgmatic.d/{app_name}.yml"
  if new_config_file not in borgmatic_config_files:
    borgmatic_config_files.append(new_config_file)
  exporter_service_env_vars["BORGMATIC_CONFIG"] = ":".join(borgmatic_config_files)

  # Dump content back to docker-compose.override.yml
  with open(docker_compose_path, "w", encoding="utf-8") as file:
    file.write(yaml.dump(docker_compose, default_flow_style=False))

def print_post_script_documentation(app_name):
  print("\nYour app is almost ready to backup!")
  print("Execute the following steps to finish the setup:")
  print("> drc up -d")
  print(f"> drc exec borgmatic borgmatic init --repository {app_name} --encryption repokey --append-only")
  print(f"> drc exec borgmatic borgmatic key export --repository {app_name}")

  print("\n####################################################################################################")
  print("  !!! Make sure to keep the exported key somewhere save together with the generated passphrase !!!")
  print("####################################################################################################")

  print("\nYou can configure the frequency of automatic backups via the 'BACKUP_CRON' env var on the borgmatic service.")
  print("To create a new backup manually:")
  print(f"> drc exec borgmatic borgmatic create --repository {app_name} --stats")

if __name__ == '__main__':
  if len(sys.argv) < 5: # sys.argv[0] is the script name. Arguments start at index 1.
    print(f"\nScript expects 4 args, only {len(sys.argv) - 1} were passed.")
    print(f"- type (one of 'app' or 'http-log')")
    print(f"- backup-server-ssh-connection (e.g. u339567-sub1@u339567.your-storagebox.de:23)")
    print(f"- server-hostname (e.g. abb-croco)")
    print(f"- app-name (e.g. app-mandatendatabank)")
    sys.exit(1)
  else:
    main()
