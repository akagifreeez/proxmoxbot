import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
from utils.api import proxmox, run_proxmox_async, get_device_node_and_type, check_access, vmid_autocomplete
from utils.plotting import generate_graph

class VMControlView(discord.ui.View):
    def __init__(self, vmid: int, node: str, vm_type: str, status: str):
        super().__init__(timeout=180)
        self.vmid = vmid
        self.node = node
        self.vm_type = vm_type

        # Start Button
        self.start_button = discord.ui.Button(
            label="Start", style=discord.ButtonStyle.green, custom_id="vm_start",
            disabled=(status == 'running')
        )
        self.start_button.callback = self.start_callback
        self.add_item(self.start_button)

        # Reboot Button
        self.reboot_button = discord.ui.Button(
            label="Reboot", style=discord.ButtonStyle.blurple, custom_id="vm_reboot",
            disabled=(status != 'running')
        )
        self.reboot_button.callback = self.reboot_callback
        self.add_item(self.reboot_button)

        # Shutdown Button
        self.shutdown_button = discord.ui.Button(
            label="Shutdown", style=discord.ButtonStyle.red, custom_id="vm_shutdown",
            disabled=(status != 'running')
        )
        self.shutdown_button.callback = self.shutdown_callback
        self.add_item(self.shutdown_button)

    async def common_action(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer()
        try:
            resource = getattr(proxmox.nodes(self.node), self.vm_type)(self.vmid)
            if action == 'start':
                await run_proxmox_async(resource.status.start.post)
                msg = f"▶️ VMID: {self.vmid} を起動しました。"
            elif action == 'reboot':
                await run_proxmox_async(resource.status.reboot.post)
                msg = f"🔄 VMID: {self.vmid} を再起動中..."
            elif action == 'shutdown':
                await run_proxmox_async(resource.status.shutdown.post)
                msg = f"🛑 VMID: {self.vmid} にシャットダウン信号を送信しました。"

            await interaction.followup.send(msg)

            # Update view state (optimistic update)
            for item in self.children:
                item.disabled = True
            await interaction.edit_original_response(view=self)

        except Exception as e:
            await interaction.followup.send(f"❌ 操作失敗: {e}")

    async def start_callback(self, interaction: discord.Interaction):
        await self.common_action(interaction, 'start')

    async def reboot_callback(self, interaction: discord.Interaction):
        await self.common_action(interaction, 'reboot')

    async def shutdown_callback(self, interaction: discord.Interaction):
        await self.common_action(interaction, 'shutdown')


class BasicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="list", description="VMの一覧とステータスを表示")
    async def list_vms(self, interaction: discord.Interaction):
        """
        Lists all Virtual Machines on the Proxmox node with their current status.
        """
        if error := check_access(interaction):
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.defer()
        try:
            vms = await run_proxmox_async(proxmox.cluster.resources.get, type='vm')
            vms.sort(key=lambda x: int(x['vmid']))

            embed = discord.Embed(title="📦 Proxmox VM/LXC List", color=discord.Color.blue())
            description_lines = []
            for vm in vms:
                status = vm.get('status')
                icon = "🟢" if status == 'running' else "🔴"
                vmid = vm.get('vmid')
                name = vm.get('name')
                vm_type = vm.get('type')
                type_icon = "🖥️" if vm_type == 'qemu' else "📦"
                description_lines.append(f"{icon} {type_icon} **{vmid}**: {name} ({vm_type})")

            embed.description = "\n".join(description_lines)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f'❌ 取得失敗: {e}')

    @app_commands.command(name="info", description="VMの詳細スペックと稼働状況を確認")
    @app_commands.describe(vmid="対象のVMID")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def info(self, interaction: discord.Interaction, vmid: int):
        """
        Retrieves and displays detailed information about a specific VM.
        """
        if error := check_access(interaction):
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.defer()
        try:
            node, vm_type = await get_device_node_and_type(vmid)
            if not node or not vm_type:
                await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
                return

            resource = getattr(proxmox.nodes(node), vm_type)(vmid)
            status = await run_proxmox_async(resource.status.current.get)
            conf = await run_proxmox_async(resource.config.get)

            vm_name = status.get('name', 'Unknown')
            vm_status = status.get('status', 'unknown')
            color = discord.Color.green() if vm_status == 'running' else discord.Color.red()

            embed = discord.Embed(title=f"ℹ️ {vm_type.upper()} Info: {vm_name}", color=color)
            embed.add_field(name="VMID", value=str(vmid), inline=True)
            embed.add_field(name="Type", value=vm_type.upper(), inline=True)
            embed.add_field(name="Status", value=vm_status.upper(), inline=True)

            cores = conf.get('cores', '?')
            cpu_usage = status.get('cpu', 0) * 100
            embed.add_field(name="CPU", value=f"{cores} Cores\nUsage: {cpu_usage:.1f}%", inline=True)

            max_mem = int(status.get('maxmem', 0)) / 1024 / 1024
            cur_mem = int(status.get('mem', 0)) / 1024 / 1024
            embed.add_field(name="Memory", value=f"{cur_mem:.0f}MB / {max_mem:.0f}MB", inline=True)

            uptime_sec = int(status.get('uptime', 0))
            uptime_str = str(timedelta(seconds=uptime_sec))
            embed.add_field(name="Uptime", value=uptime_str, inline=True)

            net0 = conf.get('net0', 'N/A')
            embed.add_field(name="Network (net0)", value=f"`{net0}`", inline=False)

            view = VMControlView(vmid, node, vm_type, vm_status)
            await interaction.followup.send(embed=embed, view=view)
        except Exception as e:
            await interaction.followup.send(f'❌ 情報取得失敗: {e}')

    @app_commands.command(name="graph", description="リソース使用状況のグラフを表示")
    @app_commands.describe(vmid="対象のVMID", timeframe="期間 (hour, day, week, month)")
    @app_commands.choices(timeframe=[
        app_commands.Choice(name="Hour", value="hour"),
        app_commands.Choice(name="Day", value="day"),
        app_commands.Choice(name="Week", value="week"),
        app_commands.Choice(name="Month", value="month")
    ])
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def graph(self, interaction: discord.Interaction, vmid: int, timeframe: str = "hour"):
        """
        Generates and displays resource usage graphs (CPU, Memory, Network) for a specific VM.
        """
        if error := check_access(interaction):
            await interaction.response.send_message(error, ephemeral=True)
            return

        await interaction.response.defer()
        try:
            node, vm_type = await get_device_node_and_type(vmid)
            if not node or not vm_type:
                await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
                return

            resource = getattr(proxmox.nodes(node), vm_type)(vmid)

            # Fetch RRD data
            rrd_data = await run_proxmox_async(resource.rrddata.get, timeframe=timeframe)

            if not rrd_data:
                await interaction.followup.send(f'⚠️ データが見つかりませんでした (Timeframe: {timeframe})')
                return

            # Get VM Name for title
            status = await run_proxmox_async(resource.status.current.get)
            vm_name = status.get('name', f'VM {vmid}')
            title = f"{vm_name} (ID: {vmid}) - Last {timeframe}"

            # Generate Graph
            image_buf = await generate_graph(rrd_data, title, timeframe)

            file = discord.File(image_buf, filename=f"graph_{vmid}_{timeframe}.png")
            await interaction.followup.send(content=f"📊 **Performance Graph**: {title}", file=file)

        except Exception as e:
            await interaction.followup.send(f'❌ グラフ生成失敗: {e}')

async def setup(bot):
    await bot.add_cog(BasicCommands(bot))
