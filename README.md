# Proxmox Discord Bot

A Discord bot to manage Proxmox Virtual Machines (VMs) and LXC Containers directly from your Discord server. This bot allows you to list, create, start, stop, resize, and delete resources, as well as monitor their status with ease.

## Features

- **Resource Support**: Supports both **QEMU VMs** and **LXC Containers**.
- **List Resources**: View all VMs and Containers on the Proxmox node with their status and type.
- **Detailed Info**: Get specifications and status of a specific resource, with interactive control buttons.
- **Create VM**: Clone a VM from a template.
- **Resize Resource**: Change the CPU cores and memory of a VM or Container.
- **Power Management**: Start, Reboot, Shutdown (ACPI), and Stop (Force) resources.
- **Snapshot Management**: Create, list, and rollback snapshots directly from Discord.
- **Dynamic Monitoring**: Add or remove resources from the monitoring list using commands without restarting the bot.
- **Autocomplete**: VMIDs are autocompleted in commands for easier usage.
- **Access Control**: Restricts commands to a specific Discord category.
- **Async I/O**: Optimized for performance with asynchronous API calls.

## Prerequisites

- Python 3.8+
- Proxmox VE server
- Discord Bot Token

## Installation

1.  Clone the repository:
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  Install the required Python packages:
    ```bash
    pip install discord.py proxmoxer urllib3
    ```

3.  Configure the bot:
    - Rename `config.py.example` to `config.py`.
    - Open `config.py` and fill in your Discord and Proxmox credentials.

    ```python
    # config.py

    # --- Discord Settings ---
    DISCORD_TOKEN = 'your_discord_bot_token'
    GUILD_ID = 123456789012345678         # Server ID
    ALLOWED_CATEGORY_ID = 123456789012345678  # Category ID where commands are allowed
    ALERT_CHANNEL_ID = 123456789012345678     # Channel ID for alerts

    # --- Proxmox Settings ---
    PROXMOX_HOST = '192.168.1.100'
    PROXMOX_USER = 'root@pam'
    PROXMOX_TOKEN_NAME = 'bot'
    PROXMOX_TOKEN_VALUE = 'xxxxx-xxxxx-xxxxx'
    NODE_NAME = 'pve'

    # --- Monitoring Settings ---
    # List of VM IDs to monitor (Initial Setup Only)
    # On first run, this list is saved to 'monitor_list.json'.
    # Subsequent management should be done via /monitor commands.
    MONITOR_VM_IDS = [100, 101, 105]
    ```

## Usage

Run the bot using Python:

```bash
python bptcode.py
```

### Commands

All commands are slash commands (`/`). VMIDs support autocomplete.

#### General
- `/list`: Displays a list of all VMs and LXC Containers with their status.
- `/info <vmid>`: Shows detailed info and provides interactive buttons (**Start**, **Reboot**, **Shutdown**) for the resource.
- `/create <template_id> <new_vmid> <name>`: Creates a new VM by cloning a template.
- `/resize <vmid> <cores> <memory_mb>`: Updates the CPU cores and memory (MB). Changes apply after a reboot.
- `/delete <vmid>`: Deletes a resource. **Warning**: This action is irreversible.

#### Power Management
- `/start <vmid>`: Starts a resource.
- `/reboot <vmid>`: Reboots a resource.
- `/shutdown <vmid>`: Sends an ACPI shutdown signal (graceful stop).
- `/stop <vmid>`: Forcefully stops the resource (power off). Requires confirmation.

#### Snapshot Management
- `/snapshot create <vmid> <name>`: Creates a snapshot.
- `/snapshot list <vmid>`: Lists all snapshots.
- `/snapshot rollback <vmid> <name>`: Rolls back to a specific snapshot (requires confirmation).

#### Monitoring Configuration
- `/monitor add <vmid>`: Adds a resource to the monitoring list.
- `/monitor remove <vmid>`: Removes a resource from the monitoring list.
- `/monitor list`: Displays currently monitored resources.

## Permissions

The bot enforces usage within a specific Discord category defined by `ALLOWED_CATEGORY_ID` in `config.py`. Ensure the channel you are using is within this category.

## Monitoring

The bot runs a background task every minute to check the status of monitored resources. If a monitored resource is found to be stopped, an alert is sent to the `ALERT_CHANNEL_ID`. The monitoring list is stored persistently in `monitor_list.json`.
