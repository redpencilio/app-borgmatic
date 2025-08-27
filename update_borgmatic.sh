#!/bin/bash

# Strict error handling
set -euo pipefail  # Exit on error, undefined vars, pipe failures
IFS=$'\n\t'       # Secure IFS

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Configuration - make these readonly for safety
readonly CONFIG_DIR="${CONFIG_DIR:-/data/app-borgmatic/config/borgmatic.d}"
readonly SSH_KEY_PATH="${SSH_KEY_PATH:-$HOME/.ssh/id_borgmatic.pub}"
readonly SSH_PORT="${SSH_PORT:-23}"
readonly YQ_URL="https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64"
readonly ACCOUNT_PATTERN='^u[0-9]+-sub[0-9]+$'

# Install yq if not present
install_yq() {
    if command -v yq &>/dev/null; then
        print_status "yq is already installed"
        return 0
    fi

    print_status "Installing yq..."

    # Create temporary file for download
    local temp_file
    temp_file=$(mktemp) || { print_error "Failed to create temp file"; return 1; }

    # Download with proper error handling
    if wget -q "$YQ_URL" -O "$temp_file" && \
       sudo install "$temp_file" /usr/local/bin/yq; then
        rm -f "$temp_file"
        print_success "yq installed successfully"
    else
        rm -f "$temp_file"
        print_error "Failed to install yq"
        return 1
    fi
}

# Validate backup account format
validate_account() {
    local -r account="$1"

    if [[ -z "$account" ]]; then
        print_error "Account cannot be empty"
        return 1
    fi

    if [[ ! $account =~ $ACCOUNT_PATTERN ]]; then
        print_error "Invalid account format '$account'. Expected format: u123456-sub1"
        return 1
    fi

    return 0
}

# Validate repository path format (username@hostname should match)
validate_repository_path() {
    local -r repo_path="$1"
    local -r config_file="$2"

    # Extract username and hostname from SSH path
    if [[ "$repo_path" =~ ssh://([^@]+)@([^.:]+) ]]; then
        local username="${BASH_REMATCH[1]}"
        local hostname="${BASH_REMATCH[2]}"

        # Check if username matches hostname
        if [[ "$username" != "$hostname" ]]; then
            print_error "Repository path validation failed in $(basename "$config_file")"
            print_error "Username '$username' does not match hostname '$hostname'"
            print_error "Expected format: ssh://u123456-sub1@u123456-sub1.your-storagebox.de:23/..."
            return 1
        fi

        # Validate account format
        if ! validate_account "$username"; then
            print_error "Invalid account format in repository path: $repo_path"
            return 1
        fi
    else
        print_error "Invalid repository path format in $(basename "$config_file"): $repo_path"
        print_error "Expected SSH format: ssh://username@hostname:port/path"
        return 1
    fi

    return 0
}

# Global associative arrays to cache parsed YAML data
declare -A CONFIG_CACHE_ACCOUNTS=()
declare -A CONFIG_CACHE_LABELS=()
declare -A CONFIG_CACHE_PATHS=()
declare -A CONFIG_CACHE_PASSPHRASES=()
declare CONFIG_PARSED="false"

# Parse all YAML config files once and cache the data
parse_config_files() {
    local -r config_dir="$1"

    if [[ ! -d "$config_dir" ]]; then
        print_error "Config directory does not exist: $config_dir"
        return 1
    fi

    print_status "Parsing configuration files..." >&2

    # Process all YAML config files
    while IFS= read -r -d '' config_file; do
        print_status "Processing $(basename "$config_file")..." >&2

        # Extract all repository data in one pass
        local repo_data
        repo_data=$(yq eval '.repositories[] | [.path, .label] | @tsv' "$config_file" 2>/dev/null || true)

        # Extract passphrase once per file
        local passphrase
        passphrase=$(yq eval '.encryption_passphrase' "$config_file" 2>/dev/null || echo "N/A")

        # Process each repository entry
        while IFS=$'\t' read -r path label; do
            if [[ -n "$path" && "$path" != "null" && -n "$label" && "$label" != "null" ]]; then
                # Validate repository path format
                if ! validate_repository_path "$path" "$config_file"; then
                    print_error "Configuration validation failed. Please fix repository paths and try again."
                    return 1
                fi

                # Extract and cache account from validated path
                if [[ "$path" =~ ssh://([^@]+)@ ]]; then
                    local account="${BASH_REMATCH[1]}"
                    CONFIG_CACHE_ACCOUNTS["$account"]=1
                    CONFIG_CACHE_LABELS["$label"]=1
                    CONFIG_CACHE_PATHS["$label"]="$path"
                    CONFIG_CACHE_PASSPHRASES["$label"]="$passphrase"
                fi
            fi
        done <<< "$repo_data"
    done < <(find "$config_dir" \( -name "*.yml" -o -name "*.yaml" \) -print0 2>/dev/null)

    return 0
}

# Extract accounts from cached data
extract_old_account() {
    local -r config_dir="$1"

    # Parse config files if not already done
    if [[ "$CONFIG_PARSED" != "true" ]]; then
        if ! parse_config_files "$config_dir"; then
            return 1
        fi
        CONFIG_PARSED="true"
    fi

    # Return unique accounts from cache
    if [[ ${#CONFIG_CACHE_ACCOUNTS[@]} -gt 0 ]]; then
        printf '%s\n' "${!CONFIG_CACHE_ACCOUNTS[@]}" | sort -u
    fi
}

# Extract repository labels from cached data
extract_repository_labels() {
    local -r config_dir="$1"

    # Parse config files if not already done
    if [[ "$CONFIG_PARSED" != "true" ]]; then
        if ! parse_config_files "$config_dir"; then
            return 1
        fi
        CONFIG_PARSED="true"
    fi

    # Return unique labels from cache
    if [[ ${#CONFIG_CACHE_LABELS[@]} -gt 0 ]]; then
        printf '%s\n' "${!CONFIG_CACHE_LABELS[@]}" | sort -u
    fi
}

# Get repository info (path or passphrase) for a given label from cache
get_repository_info() {
    local -r config_dir="$1"
    local -r target_label="$2"
    local -r info_type="$3"  # "path" or "passphrase"

    # Parse config files if not already done
    if [[ "$CONFIG_PARSED" != "true" ]]; then
        if ! parse_config_files "$config_dir"; then
            return 1
        fi
        CONFIG_PARSED="true"
    fi

    # Return data from cache
    if [[ "$info_type" == "path" ]]; then
        echo "${CONFIG_CACHE_PATHS[$target_label]:-}"
    else
        echo "${CONFIG_CACHE_PASSPHRASES[$target_label]:-N/A}"
    fi
}

# Update config files by replacing old account with new account
update_config_files() {
    local -r old_account="$1"
    local -r new_account="$2"
    local -r config_dir="$3"
    local files_updated=0

    print_status "Updating configuration files in $config_dir"

    if [[ ! -d "$config_dir" ]]; then
        print_error "Config directory does not exist: $config_dir"
        return 1
    fi

    # Process all YAML config files
    while IFS= read -r -d '' config_file; do
        if grep -q "$old_account" "$config_file"; then
            print_status "Updating $(basename "$config_file")"

            # Create timestamped backup
            local backup_file="${config_file}.backup.$(date +%Y%m%d_%H%M%S)"
            if ! cp "$config_file" "$backup_file"; then
                print_error "Failed to create backup of $config_file"
                return 1
            fi

            # Replace old account with new account (using safer sed syntax)
            if sed -i "s|$old_account|$new_account|g" "$config_file"; then
                ((files_updated++))
                print_success "Updated $(basename "$config_file")"
            else
                print_error "Failed to update $config_file"
                return 1
            fi
        fi
    done < <(find "$config_dir" \( -name "*.yml" -o -name "*.yaml" \) -print0 2>/dev/null)

    if [[ $files_updated -eq 0 ]]; then
        print_warning "No files contained the old account '$old_account'"
    else
        print_success "Updated $files_updated configuration file(s)"
    fi
}

# Setup SSH key with restricted shell access
setup_ssh_key() {
    local -r new_account="$1"
    local -r ssh_host="${new_account}.your-storagebox.de"
    local -r port="$SSH_PORT"

    print_status "Setting up restricted SSH key for $new_account@$ssh_host:$port"

    # Validate SSH public key exists
    if [[ ! -f "$SSH_KEY_PATH" ]]; then
        print_error "SSH public key not found at $SSH_KEY_PATH"
        return 1
    fi

    if [[ ! -r "$SSH_KEY_PATH" ]]; then
        print_error "SSH public key is not readable at $SSH_KEY_PATH"
        return 1
    fi

    print_status "Configuring restricted borg shell access..."

    # Create temporary file for authorized_keys manipulation
    local temp_auth_keys
    temp_auth_keys=$(mktemp) || { print_error "Failed to create temp file"; return 1; }

    # Use sftp to set up restricted shell with better error handling
    local sftp_script
    sftp_script=$(cat <<EOF
mkdir .ssh
get .ssh/authorized_keys "$temp_auth_keys"
bye
EOF
)

    if echo "$sftp_script" | sftp -q -P "$port" -o StrictHostKeyChecking=accept-new "$new_account@$ssh_host" &>/dev/null; then
        # Ensure file exists and add key if not present
        touch "$temp_auth_keys"
        local pubkey_content
        pubkey_content=$(cat "$SSH_KEY_PATH")

        if ! grep -Fq "$pubkey_content" "$temp_auth_keys"; then
            echo "command=\"borg serve --umask=077 --info\",restrict $pubkey_content" >> "$temp_auth_keys"
        fi

        # Upload the updated authorized_keys
        if echo "put \"$temp_auth_keys\" .ssh/authorized_keys" | sftp -q -P "$port" "$new_account@$ssh_host" &>/dev/null; then
            print_success "SSH key with restricted shell configured successfully"
            rm -f "$temp_auth_keys"
        else
            rm -f "$temp_auth_keys"
            print_error "Failed to upload authorized_keys"
            return 1
        fi
    else
        rm -f "$temp_auth_keys"
        print_error "Failed to configure SSH key with restricted shell"
        return 1
    fi
}

# Function to initialize repositories and export keys using labels
init_repositories() {
    local repository_labels=("$@")

    if [[ ${#repository_labels[@]} -eq 0 ]]; then
        print_warning "No repository labels found to initialize"
        return 0
    fi

    print_status "Initializing ${#repository_labels[@]} repositories..."

    # Prepare table headers
    printf "\n"
    printf "%-30s %-15s %-15s\n" "Repository Label" "Init Status" "Key Export"
    printf "%s\n" "$(seq -s= 60|tr -d '[:digit:]')"

    local results=()

    for label in "${repository_labels[@]}"; do
        local init_status="FAILED"
        local key_export="FAILED"

        print_status "Initializing repository with label: $label"

        # Initialize repository using label
        if docker compose exec borgmatic borgmatic init --repository "$label" --encryption repokey --append-only &>/dev/null; then
            init_status="SUCCESS"
            print_success "Repository $label initialized"

            # Export key if initialization succeeded
            print_status "Exporting key for repository label: $label"
            local key_output
            if key_output=$(docker compose exec borgmatic borgmatic key export --repository "$label" 2>/dev/null); then
                key_export="SUCCESS"
                # Store the key output for later display (preserve newlines with base64)
                local encoded_key
                encoded_key=$(echo "$key_output" | base64 -w 0)
                results+=("$label|$init_status|$key_export|$encoded_key")
            else
                results+=("$label|$init_status|FAILED|")
            fi
        else
            print_error "Failed to initialize repository: $label"
            results+=("$label|FAILED|SKIPPED|")
        fi

        # Print table row
        printf "%-30s %-15s %-15s\n" "${label:0:29}" "$init_status" "$key_export"
    done

    printf "%s\n" "$(seq -s= 60|tr -d '[:digit:]')"

    # Display results in org-mode table format
    printf "\n"
    print_status "Repository Summary:"
    printf "\n|%-35s|%-110s|%-142s|%-73s|\n" "Label" "Repository Path" "Encryption Passphrase" "Borg Key"
    printf "|%s+%s+%s+%s|\n" "$(seq -s- 36|tr -d '[:digit:]')" "$(seq -s- 111|tr -d '[:digit:]')" "$(seq -s- 143|tr -d '[:digit:]')" "$(seq -s- 74|tr -d '[:digit:]')"

    for result in "${results[@]}"; do
        IFS='|' read -r label init_status key_status encoded_key_data <<< "$result"
        if [[ "$key_status" == "SUCCESS" && -n "$encoded_key_data" ]]; then
            # Decode the key data
            local key_data
            key_data=$(echo "$encoded_key_data" | base64 -d 2>/dev/null || echo "$encoded_key_data")

            # Get repository path and passphrase for this label
            local repo_path
            repo_path=$(get_repository_info "$CONFIG_DIR" "$label" "path")
            local passphrase
            passphrase=$(get_repository_info "$CONFIG_DIR" "$label" "passphrase")

            # Split borg key into lines
            local -a key_lines
            mapfile -t key_lines <<< "$key_data"

            # First row with label and repo path
            printf "|%-35s|%-110s|%-142s|%-73s|\n" "$label" "$repo_path" "$passphrase" "${key_lines[0]:-}"

            # Additional rows for remaining key lines
            for ((i=1; i<${#key_lines[@]}; i++)); do
                printf "|%-35s|%-110s|%-142s|%-73s|\n" "" "" "" "${key_lines[i]}"
            done
        fi
    done
    printf "|%s+%s+%s+%s|\n" "$(seq -s- 36|tr -d '[:digit:]')" "$(seq -s- 111|tr -d '[:digit:]')" "$(seq -s- 143|tr -d '[:digit:]')" "$(seq -s- 74|tr -d '[:digit:]')"
}

# Main script
main() {
    print_status "Borgmatic Configuration Update Script"
    printf "%s\n" "$(seq -s= 50|tr -d '[:digit:]')"

    # Install yq if needed
    if ! install_yq; then
        print_error "yq installation failed and yq is required for this script"
        exit 1
    fi

    # Validate prerequisites
    if [[ ! -d "$CONFIG_DIR" ]]; then
        print_error "Configuration directory $CONFIG_DIR not found"
        exit 1
    fi

    if ! command -v docker &> /dev/null; then
        print_error "Docker not found. Please install docker."
        exit 1
    fi

    if ! command -v yq &> /dev/null; then
        print_error "yq not found. Please install yq for YAML parsing."
        exit 1
    fi

    # Extract old account from existing repository paths
    print_status "Extracting old account from repository configurations..."
    local old_accounts
    mapfile -t old_accounts < <(extract_old_account "$CONFIG_DIR")

    if [[ ${#old_accounts[@]} -eq 0 ]]; then
        print_error "No backup accounts found in repository configurations"
        exit 1
    fi

    local old_account
    if [[ ${#old_accounts[@]} -gt 1 ]]; then
        print_warning "Multiple accounts found: ${old_accounts[*]}"
        print_status "Please select the old account to replace:"
        select old_account in "${old_accounts[@]}" "Cancel"; do
            case $old_account in
                "Cancel") print_status "Operation cancelled"; exit 0 ;;
                *) if [[ -n "$old_account" ]]; then break; fi ;;
            esac
        done
    else
        old_account="${old_accounts[0]}"
        print_status "Found old account: $old_account"
    fi

    # Get new account with validation
    local new_account
    while true; do
        read -rp "Enter new backup account (e.g., u487286-sub2): " new_account
        if validate_account "$new_account"; then
            break
        fi
        print_error "Please try again with correct format"
    done

    if [[ "$old_account" == "$new_account" ]]; then
        print_error "Old and new accounts are the same"
        exit 1
    fi

    # Confirmation
    echo
    print_warning "This will:"
    echo "  1. Update all .yml/.yaml files in $CONFIG_DIR"
    echo "  2. Replace '$old_account' with '$new_account'"
    echo "  3. Copy SSH key to the new account"
    echo "  4. Initialize all found repositories"
    echo "  5. Export keys for all repositories"
    echo
    read -p "Continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Operation cancelled"
        exit 0
    fi

    # Extract repository labels before updating configs
    print_status "Extracting repository labels from current configuration..."
    local repository_labels
    mapfile -t repository_labels < <(extract_repository_labels "$CONFIG_DIR")

    if [[ ${#repository_labels[@]} -eq 0 ]]; then
        print_warning "No repository labels found in configuration files"
    else
        print_status "Found ${#repository_labels[@]} repository labels:"
        printf "  %s\n" "${repository_labels[@]}"
    fi

    # Update configuration files
    echo
    if ! update_config_files "$old_account" "$new_account" "$CONFIG_DIR"; then
        print_error "Failed to update configuration files"
        exit 1
    fi

    # Setup SSH key
    echo
    setup_ssh_key "$new_account"

    # Initialize repositories and export keys
    if [[ ${#repository_labels[@]} -gt 0 ]]; then
        echo
        read -p "Initialize repositories and export keys? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            init_repositories "${repository_labels[@]}"
        else
            print_status "Skipped repository initialization"
        fi
    fi

    echo
    print_success "Borgmatic configuration update completed!"
    print_status "Backup files created with timestamp suffix"
}

# Run main function
main "$@"
