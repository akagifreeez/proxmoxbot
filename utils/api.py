import asyncio
import urllib3
from proxmoxer import ProxmoxAPI
import discord
from discord import app_commands
import config

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class AsyncProxmox:
    def __init__(self):
        self.proxmox = ProxmoxAPI(
            config.PROXMOX_HOST,
            user=config.PROXMOX_USER,
            token_name=config.PROXMOX_TOKEN_NAME,
            token_value=config.PROXMOX_TOKEN_VALUE,
            verify_ssl=False
        )

    async def run_blocking(self, func, *args, **kwargs):
        """
        Runs a synchronous Proxmox API call in a separate thread to avoid blocking the event loop.
        同期的なProxmox API呼び出しを別スレッドで実行し、イベントループのブロックを防ぎます。
        """
        return await asyncio.get_running_loop().run_in_executor(None, lambda: func(*args, **kwargs))

    @property
    def client(self):
        return self.proxmox

# Global instance
proxmox_wrapper = AsyncProxmox()

async def get_device_node_and_type(vmid: int):
    """
    Returns (node_name, type) for a given VMID.
    Type is 'qemu' or 'lxc'.
    Returns (None, None) if not found.
    """
    try:
        resources = await proxmox_wrapper.run_blocking(proxmox_wrapper.client.cluster.resources.get, type='vm')
        for res in resources:
            if int(res.get('vmid')) == int(vmid):
                return res.get('node'), res.get('type')
    except Exception as e:
        print(f"Error getting resource type: {e}")
    return None, None

async def vmid_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    """
    Autocompletes VMID based on the user's input.
    ユーザー入力に基づいてVMIDをオートコンプリートします。
    """
    try:
        resources = await proxmox_wrapper.run_blocking(proxmox_wrapper.client.cluster.resources.get, type='vm')
        choices = []
        for res in resources:
            vmid = str(res.get('vmid'))
            name = res.get('name', 'Unknown')
            # Filter matches
            if current in vmid or current.lower() in name.lower():
                display_name = f"{vmid}: {name} ({res.get('type')})"
                choices.append(app_commands.Choice(name=display_name, value=int(vmid)))

        return choices[:25]
    except Exception as e:
        print(f"Autocomplete Error: {e}")
        return []
