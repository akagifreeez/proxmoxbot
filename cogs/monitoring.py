import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import config
from utils.api import proxmox, run_proxmox_async, get_device_node_and_type, check_access, vmid_autocomplete

MONITOR_LIST_FILE = 'monitor_list.json'

def load_monitor_list() -> list[int]:
    """Loads the list of monitored VMIDs from a JSON file."""
    if not os.path.exists(MONITOR_LIST_FILE):
        # Initialize with config values if file doesn't exist
        initial_list = getattr(config, 'MONITOR_VM_IDS', [])
        save_monitor_list(initial_list)
        return initial_list
    try:
        with open(MONITOR_LIST_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading monitor list: {e}")
        return []

def save_monitor_list(ids: list[int]):
    """Saves the list of monitored VMIDs to a JSON file."""
    try:
        with open(MONITOR_LIST_FILE, 'w') as f:
            json.dump(ids, f)
    except Exception as e:
        print(f"Error saving monitor list: {e}")

class Monitoring(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monitor_vms.start()

    def cog_unload(self):
        self.monitor_vms.cancel()

    @tasks.loop(minutes=1)
    async def monitor_vms(self):
        """
        A background task that checks the status of monitored VMs every minute.
        """
        channel = self.bot.get_channel(config.ALERT_CHANNEL_ID)
        if not channel: return

        monitored_ids = load_monitor_list()

        for vmid in monitored_ids:
            try:
                node, vm_type = await get_device_node_and_type(vmid)
                if not node or not vm_type:
                    continue

                resource = getattr(proxmox.nodes(node), vm_type)(vmid)
                status_data = await run_proxmox_async(resource.status.current.get)

                if status_data.get('status') == 'stopped':
                    await channel.send(f'🚨 **緊急**: VMID {vmid} ({status_data.get("name")}) が停止しています！')
            except Exception as e:
                print(f"Monitor Error {vmid}: {e}")

    @monitor_vms.before_loop
    async def before_monitor(self):
        await self.bot.wait_until_ready()

    # Monitoring Group Commands
    monitor_group = app_commands.Group(name="monitor", description="監視対象の管理")

    @monitor_group.command(name="add", description="監視対象に追加")
    @app_commands.describe(vmid="対象のVMID")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def monitor_add(self, interaction: discord.Interaction, vmid: int):
        """
        Adds a VMID to the monitoring list.
        """
        if error := check_access(interaction):
            await interaction.response.send_message(error, ephemeral=True)
            return

        current_list = load_monitor_list()
        if vmid in current_list:
            await interaction.response.send_message(f"⚠️ VMID {vmid} は既に監視対象です。", ephemeral=True)
            return

        # Check if VM exists
        node, vm_type = await get_device_node_and_type(vmid)
        if not node:
             await interaction.response.send_message(f"❌ VMID {vmid} が見つかりません。", ephemeral=True)
             return

        current_list.append(vmid)
        save_monitor_list(current_list)
        await interaction.response.send_message(f"✅ 監視対象に追加: VMID {vmid}")

    @monitor_group.command(name="remove", description="監視対象から削除")
    @app_commands.describe(vmid="対象のVMID")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def monitor_remove(self, interaction: discord.Interaction, vmid: int):
        """
        Removes a VMID from the monitoring list.
        """
        if error := check_access(interaction):
            await interaction.response.send_message(error, ephemeral=True)
            return

        current_list = load_monitor_list()
        if vmid not in current_list:
            await interaction.response.send_message(f"⚠️ VMID {vmid} は監視対象ではありません。", ephemeral=True)
            return

        current_list.remove(vmid)
        save_monitor_list(current_list)
        await interaction.response.send_message(f"🗑️ 監視対象から削除: VMID {vmid}")

    @monitor_group.command(name="list", description="監視対象一覧")
    async def monitor_list_cmd(self, interaction: discord.Interaction):
        """
        Lists all monitored VMIDs.
        """
        if error := check_access(interaction):
            await interaction.response.send_message(error, ephemeral=True)
            return

        current_list = load_monitor_list()
        if not current_list:
            await interaction.response.send_message("監視対象はありません。")
            return

        await interaction.response.defer()

        embed = discord.Embed(title="👀 Monitored VMs", color=discord.Color.gold())
        lines = []

        # Try to resolve names
        resources = await run_proxmox_async(proxmox.cluster.resources.get, type='vm')
        resource_map = {int(r['vmid']): r for r in resources}

        for vmid in current_list:
            res = resource_map.get(vmid)
            if res:
                 lines.append(f"• **{vmid}**: {res.get('name')} ({res.get('type')}) - {res.get('status')}")
            else:
                 lines.append(f"• **{vmid}**: (Unknown/Deleted)")

        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Monitoring(bot))
