# Proxmox Discord Bot

A Discord bot to manage Proxmox Virtual Machines (VMs) directly from your Discord server. This bot allows you to list, create, start, stop, resize, and delete VMs, as well as monitor their status.

## Features

- **List VMs**: View all VMs on the Proxmox node with their status.
- **VM Info**: Get detailed specifications and status of a specific VM.
- **Create VM**: Clone a VM from a template.
- **Resize VM**: Change the CPU cores and memory of a VM.
- **Power Management**: Start and reboot VMs.
- **Delete VM**: Delete a VM (with a safety stop).
- **Monitoring**: Periodically checks the status of specified VMs and sends an alert if they are stopped.
- **Access Control**: Restricts commands to a specific Discord category.

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
    # List of VM IDs to monitor
    MONITOR_VM_IDS = [100, 101, 105]
    ```

## Usage

Run the bot using Python:

```bash
python bptcode.py
```

### Commands

All commands are slash commands (`/`).

- `/list`: Displays a list of all VMs and their status.
- `/info <vmid>`: Shows detailed information about a VM (CPU, Memory, Uptime, etc.).
- `/create <template_id> <new_vmid> <name>`: Creates a new VM by cloning a template.
- `/resize <vmid> <cores> <memory_mb>`: Updates the CPU cores and memory (MB) for a VM. Changes apply after a reboot.
- `/start <vmid>`: Starts a stopped VM.
- `/reboot <vmid>`: Reboots a running VM.
- `/delete <vmid>`: Deletes a VM. **Warning**: This action is irreversible.

## Permissions

The bot enforces usage within a specific Discord category defined by `ALLOWED_CATEGORY_ID` in `config.py`. Ensure the channel you are using is within this category.

## Monitoring

The bot runs a background task every minute to check the status of VMs listed in `MONITOR_VM_IDS`. If a monitored VM is found to be stopped, an alert is sent to the `ALERT_CHANNEL_ID`.
