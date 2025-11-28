import asyncio
from proxmoxer import ProxmoxAPI
import urllib3
import config

# SSL証明書エラーの警告を無視
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize Proxmox API
proxmox = ProxmoxAPI(
    config.PROXMOX_HOST,
    user=config.PROXMOX_USER,
    token_name=config.PROXMOX_TOKEN_NAME,
    token_value=config.PROXMOX_TOKEN_VALUE,
    verify_ssl=False
)

async def run_proxmox_async(func, *args, **kwargs):
    """
    Runs a synchronous Proxmox API call in a separate thread.
    """
    return await asyncio.get_running_loop().run_in_executor(None, lambda: func(*args, **kwargs))

async def get_device_node_and_type(vmid: int):
    """
    Returns (node_name, type) for a given VMID.
    Type is 'qemu' or 'lxc'.
    Returns (None, None) if not found.
    """
    try:
        resources = await run_proxmox_async(proxmox.cluster.resources.get, type='vm')
        for res in resources:
            if int(res.get('vmid')) == int(vmid):
                return res.get('node'), res.get('type')
    except Exception as e:
        print(f"Error getting resource type: {e}")
    return None, None

def check_access(interaction) -> str | None:
    """
    Checks if the command is being invoked in an allowed category.
    """
    category_id = getattr(interaction.channel, 'category_id', None)
    if category_id != config.ALLOWED_CATEGORY_ID:
        return "❌ このコマンドは指定された管理カテゴリ内のチャンネルでのみ使用可能です。"
    return None

async def vmid_autocomplete(interaction, current: str):
    """
    Autocompletes VMID based on the user's input.
    """
    try:
        resources = await run_proxmox_async(proxmox.cluster.resources.get, type='vm')
        choices = []
        for res in resources:
            vmid = str(res.get('vmid'))
            name = res.get('name', 'Unknown')
            if current in vmid or current.lower() in name.lower():
                from discord import app_commands # Import here to avoid circular dependencies if any, or just standard import
                display_name = f"{vmid}: {name} ({res.get('type')})"
                choices.append(app_commands.Choice(name=display_name, value=int(vmid)))
        return choices[:25]
    except Exception as e:
        print(f"Autocomplete Error: {e}")
        return []
