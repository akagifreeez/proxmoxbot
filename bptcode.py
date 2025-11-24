import discord
from discord import app_commands
from discord.ext import commands, tasks
from proxmoxer import ProxmoxAPI
import urllib3
import asyncio
from datetime import timedelta
import config  # 作成したconfig.pyをインポート

# SSL証明書エラーの警告を無視
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Proxmox API 接続 ---
proxmox = ProxmoxAPI(
    config.PROXMOX_HOST,
    user=config.PROXMOX_USER,
    token_name=config.PROXMOX_TOKEN_NAME,
    token_value=config.PROXMOX_TOKEN_VALUE,
    verify_ssl=False
)

# --- Bot Class定義 ---
class ProxmoxBot(commands.Bot):
    """
    A custom Discord Bot class that manages Proxmox Virtual Machines.
    Proxmox仮想マシンを管理するカスタムDiscord Botクラスです。

    This class extends `commands.Bot` to include specific setup hooks and
    background tasks for monitoring VM status.
    `commands.Bot`を拡張し、特定のセットアップフックとVMステータス監視用の
    バックグラウンドタスクを含めています。
    """
    def __init__(self):
        """
        Initializes the ProxmoxBot with specific intents and command prefix.
        特定のIntentsとコマンドプレフィックスを使用してProxmoxBotを初期化します。

        The bot is configured to listen to message content and use '!' as the
        command prefix (though most commands are slash commands).
        Botはメッセージ内容を読み取るように設定され、コマンドプレフィックスとして
        '!'を使用します（ただし、ほとんどのコマンドはスラッシュコマンドです）。
        """
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        """
        A hook called after the bot has logged in but before it connects to the WebSocket.
        Botがログインした後、WebSocketに接続する前に呼び出されるフックです。

        This method syncs the slash commands to the guild specified in the configuration
        and starts the VM monitoring background task if it's not already running.
        このメソッドは、設定で指定されたギルドにスラッシュコマンドを同期し、
        VM監視バックグラウンドタスクが実行されていない場合は開始します。
        """
        # config.GUILD_ID を使用
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("Slash commands synced!")

        if not self.monitor_vms.is_running():
            self.monitor_vms.start()

    # --- 異常監視タスク ---
    @tasks.loop(minutes=1)
    async def monitor_vms(self):
        """
        A background task that checks the status of monitored VMs every minute.
        監視対象VMのステータスを1分ごとにチェックするバックグラウンドタスクです。

        If a VM listed in `config.MONITOR_VM_IDS` is found to be in a 'stopped' state,
        an alert message is sent to the configured alert channel.
        `config.MONITOR_VM_IDS` に記載されたVMが「停止(stopped)」状態である場合、
        設定された通知チャンネルにアラートメッセージを送信します。
        """
        channel = self.get_channel(config.ALERT_CHANNEL_ID)
        if not channel: return

        # config.MONITOR_VM_IDS を使用
        for vmid in config.MONITOR_VM_IDS:
            try:
                status_data = proxmox.nodes(config.NODE_NAME).qemu(vmid).status.current.get()
                if status_data.get('status') == 'stopped':
                    await channel.send(f'🚨 **緊急**: VMID {vmid} ({status_data.get("name")}) が停止しています！')
            except Exception as e:
                print(f"Monitor Error {vmid}: {e}")

    @monitor_vms.before_loop
    async def before_monitor(self):
        """
        A hook called before the `monitor_vms` loop starts.
        `monitor_vms` ループが開始する前に呼び出されるフックです。

        Waits until the bot is fully ready before starting the monitoring loop.
        監視ループを開始する前に、Botの準備が完了するのを待ちます。
        """
        await self.wait_until_ready()

bot = ProxmoxBot()

# --- 共通チェック関数 ---
def check_access(interaction: discord.Interaction) -> str | None:
    """
    Checks if the command is being invoked in an allowed category.
    コマンドが許可されたカテゴリ内で実行されているかを確認します。

    Args:
        interaction (discord.Interaction): The interaction object representing the command invocation.
            コマンド呼び出しを表すインタラクションオブジェクト。

    Returns:
        str | None: An error message if the access is denied, or None if allowed.
            アクセスが拒否された場合はエラーメッセージ、許可された場合はNone。
    """
    # カテゴリIDチェック
    category_id = getattr(interaction.channel, 'category_id', None)

    # config.ALLOWED_CATEGORY_ID と比較
    if category_id != config.ALLOWED_CATEGORY_ID:
        return "❌ このコマンドは指定された管理カテゴリ内のチャンネルでのみ使用可能です。"
    return None

# --- コマンド定義 ---

# 1. 一覧表示 (/list)
@bot.tree.command(name="list", description="VMの一覧とステータスを表示")
async def list_vms(interaction: discord.Interaction):
    """
    Lists all Virtual Machines on the Proxmox node with their current status.
    Proxmoxノード上のすべての仮想マシンと現在のステータスを一覧表示します。

    Args:
        interaction (discord.Interaction): The interaction object.
            インタラクションオブジェクト。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        vms = proxmox.nodes(config.NODE_NAME).qemu.get()
        vms.sort(key=lambda x: int(x['vmid']))

        embed = discord.Embed(title="📦 Proxmox VM List", color=discord.Color.blue())
        description_lines = []
        for vm in vms:
            status = vm.get('status')
            icon = "🟢" if status == 'running' else "🔴"
            vmid = vm.get('vmid')
            name = vm.get('name')
            description_lines.append(f"{icon} **{vmid}**: {name}")

        embed.description = "\n".join(description_lines)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f'❌ 取得失敗: {e}')

# 2. 詳細情報 (/info)
@bot.tree.command(name="info", description="VMの詳細スペックと稼働状況を確認")
@app_commands.describe(vmid="対象のVMID")
async def info(interaction: discord.Interaction, vmid: int):
    """
    Retrieves and displays detailed information about a specific VM.
    特定のVMに関する詳細情報を取得して表示します。

    Args:
        interaction (discord.Interaction): The interaction object.
            インタラクションオブジェクト。
        vmid (int): The ID of the Virtual Machine to check.
            確認対象の仮想マシンID。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        status = proxmox.nodes(config.NODE_NAME).qemu(vmid).status.current.get()
        conf = proxmox.nodes(config.NODE_NAME).qemu(vmid).config.get()

        vm_name = status.get('name', 'Unknown')
        vm_status = status.get('status', 'unknown')
        color = discord.Color.green() if vm_status == 'running' else discord.Color.red()

        embed = discord.Embed(title=f"ℹ️ VM Info: {vm_name}", color=color)
        embed.add_field(name="VMID", value=str(vmid), inline=True)
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

        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f'❌ 情報取得失敗: {e}')

# 3. VM作成 (/create)
@bot.tree.command(name="create", description="テンプレートからVMを作成")
@app_commands.describe(template_id="クローン元VMID", new_vmid="新VMID", name="新VM名")
async def create(interaction: discord.Interaction, template_id: int, new_vmid: int, name: str):
    """
    Creates a new VM by cloning an existing template.
    既存のテンプレートをクローンして新しいVMを作成します。

    Args:
        interaction (discord.Interaction): The interaction object.
            インタラクションオブジェクト。
        template_id (int): The VMID of the template to clone.
            クローン元のテンプレートVMID。
        new_vmid (int): The VMID for the new VM.
            新しいVMのVMID。
        name (str): The name for the new VM.
            新しいVMの名前。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(config.NODE_NAME).qemu(template_id).clone.post(
            newid=new_vmid, name=name, full=1
        )
        await interaction.followup.send(
            f'✅ **作成完了**: `{name}` (ID: {new_vmid})\n'
            f'Cloud-Init設定により起動後にTailscaleへ接続されます。\n'
            f'起動コマンド: `/start vmid:{new_vmid}`'
        )
    except Exception as e:
        await interaction.followup.send(f'❌ 作成失敗: {e}')

# 4. リソース変更 (/resize)
@bot.tree.command(name="resize", description="スペック変更 (再起動後反映)")
async def resize(interaction: discord.Interaction, vmid: int, cores: int, memory_mb: int):
    """
    Updates the CPU cores and memory allocation for a specific VM.
    特定のVMのCPUコア数とメモリ割り当てを更新します。

    Note: The changes will take effect after the VM is rebooted.
    注意: 変更はVMの再起動後に反映されます。

    Args:
        interaction (discord.Interaction): The interaction object.
            インタラクションオブジェクト。
        vmid (int): The VMID of the VM to resize.
            リサイズ対象のVMID。
        cores (int): The new number of CPU cores.
            新しいCPUコア数。
        memory_mb (int): The new memory size in Megabytes (MB).
            新しいメモリサイズ(MB)。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(config.NODE_NAME).qemu(vmid).config.post(cores=cores, memory=memory_mb)
        await interaction.followup.send(f'⚙️ **設定変更**: VMID {vmid} → {cores} Cores, {memory_mb} MB\n⚠️ 再起動後に適用されます。')
    except Exception as e:
        await interaction.followup.send(f'❌ 変更失敗: {e}')

# 5. 起動 (/start)
@bot.tree.command(name="start", description="VMを起動")
async def start(interaction: discord.Interaction, vmid: int):
    """
    Starts a Virtual Machine.
    仮想マシンを起動します。

    Args:
        interaction (discord.Interaction): The interaction object.
            インタラクションオブジェクト。
        vmid (int): The VMID of the VM to start.
            起動するVMのVMID。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(config.NODE_NAME).qemu(vmid).status.start.post()
        await interaction.followup.send(f'▶️ VMID: {vmid} を起動しました。')
    except Exception as e:
        await interaction.followup.send(f'❌ 起動失敗: {e}')

# 6. 再起動 (/reboot)
@bot.tree.command(name="reboot", description="VMを再起動")
async def reboot(interaction: discord.Interaction, vmid: int):
    """
    Reboots a Virtual Machine.
    仮想マシンを再起動します。

    Args:
        interaction (discord.Interaction): The interaction object.
            インタラクションオブジェクト。
        vmid (int): The VMID of the VM to reboot.
            再起動するVMのVMID。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(config.NODE_NAME).qemu(vmid).status.reboot.post()
        await interaction.followup.send(f'🔄 VMID: {vmid} を再起動中...')
    except Exception as e:
        await interaction.followup.send(f'❌ 再起動失敗: {e}')

# 7. 削除 (/delete)
@bot.tree.command(name="delete", description="VMを削除 (警告: データ消失)")
async def delete(interaction: discord.Interaction, vmid: int):
    """
    Deletes a Virtual Machine.
    仮想マシンを削除します。

    This command attempts to stop the VM before deleting it.
    Warning: This action is irreversible and causes data loss.
    このコマンドは削除前にVMを停止しようと試みます。
    警告: この操作は取り消すことができず、データが消失します。

    Args:
        interaction (discord.Interaction): The interaction object.
            インタラクションオブジェクト。
        vmid (int): The VMID of the VM to delete.
            削除するVMのVMID。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        try:
            proxmox.nodes(config.NODE_NAME).qemu(vmid).status.stop.post()
            await asyncio.sleep(2)
        except:
            pass
        proxmox.nodes(config.NODE_NAME).qemu(vmid).delete()
        await interaction.followup.send(f'🗑️ **削除完了**: VMID {vmid} を削除しました。')
    except Exception as e:
        await interaction.followup.send(f'❌ 削除失敗: {e}')

bot.run(config.DISCORD_TOKEN)
