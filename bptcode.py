import discord
from discord import app_commands
from discord.ext import commands, tasks
from proxmoxer import ProxmoxAPI
import urllib3
import asyncio
import json
import os
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

# --- 非同期ラッパー ---
async def run_proxmox_async(func, *args, **kwargs):
    """
    Runs a synchronous Proxmox API call in a separate thread to avoid blocking the event loop.
    同期的なProxmox API呼び出しを別スレッドで実行し、イベントループのブロックを防ぎます。
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

        If a VM listed in the persistent monitoring list is found to be in a 'stopped' state,
        an alert message is sent to the configured alert channel.
        永続化された監視リストに記載されたVMが「停止(stopped)」状態である場合、
        設定された通知チャンネルにアラートメッセージを送信します。
        """
        channel = self.get_channel(config.ALERT_CHANNEL_ID)
        if not channel: return

        monitored_ids = load_monitor_list()

        for vmid in monitored_ids:
            try:
                node, vm_type = await get_device_node_and_type(vmid)
                if not node or not vm_type:
                    continue

                # Async wrapper usage
                resource = getattr(proxmox.nodes(node), vm_type)(vmid)
                status_data = await run_proxmox_async(resource.status.current.get)

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

# --- 監視リスト管理関数 ---
MONITOR_LIST_FILE = 'monitor_list.json'

def load_monitor_list() -> list[int]:
    """Loads the list of monitored VMIDs from a JSON file."""
    if not os.path.exists(MONITOR_LIST_FILE):
        # Initialize with config values if file doesn't exist
        save_monitor_list(config.MONITOR_VM_IDS)
        return config.MONITOR_VM_IDS
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
        # Use cluster resources to get both qemu and lxc
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

# 共通オートコンプリート関数
async def vmid_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    """
    Autocompletes VMID based on the user's input.
    ユーザー入力に基づいてVMIDをオートコンプリートします。
    """
    try:
        # Fetch all VMs and LXCs
        resources = await run_proxmox_async(proxmox.cluster.resources.get, type='vm')
        choices = []
        for res in resources:
            vmid = str(res.get('vmid'))
            name = res.get('name', 'Unknown')
            # Filter matches
            if current in vmid or current.lower() in name.lower():
                display_name = f"{vmid}: {name} ({res.get('type')})"
                choices.append(app_commands.Choice(name=display_name, value=int(vmid)))

        # Limit to 25 choices (Discord limit)
        return choices[:25]
    except Exception as e:
        print(f"Autocomplete Error: {e}")
        return []

# --- Interactive Views ---

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
                 # Using graceful shutdown (shutdown) not stop
                await run_proxmox_async(resource.status.shutdown.post)
                msg = f"🛑 VMID: {self.vmid} にシャットダウン信号を送信しました。"

            await interaction.followup.send(msg)

            # Update view state (optimistic update)
            # In a real scenario, we might want to fetch status again or disable buttons
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


# 2. 詳細情報 (/info)
@bot.tree.command(name="info", description="VMの詳細スペックと稼働状況を確認")
@app_commands.describe(vmid="対象のVMID")
@app_commands.autocomplete(vmid=vmid_autocomplete)
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

# 3. VM作成 (/create)
@bot.tree.command(name="create", description="テンプレートからVMを作成")
@app_commands.describe(template_id="クローン元VMID", new_vmid="新VMID", name="新VM名")
@app_commands.autocomplete(template_id=vmid_autocomplete)
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
        await run_proxmox_async(
            proxmox.nodes(config.NODE_NAME).qemu(template_id).clone.post,
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
@app_commands.autocomplete(vmid=vmid_autocomplete)
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
        node, vm_type = await get_device_node_and_type(vmid)
        if not node or not vm_type:
            await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
            return

        resource = getattr(proxmox.nodes(node), vm_type)(vmid)
        await run_proxmox_async(resource.config.post, cores=cores, memory=memory_mb)
        await interaction.followup.send(f'⚙️ **設定変更**: VMID {vmid} → {cores} Cores, {memory_mb} MB\n⚠️ 再起動後に適用されます。')
    except Exception as e:
        await interaction.followup.send(f'❌ 変更失敗: {e}')

# 5. 起動 (/start)
@bot.tree.command(name="start", description="VMを起動")
@app_commands.autocomplete(vmid=vmid_autocomplete)
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
        node, vm_type = await get_device_node_and_type(vmid)
        if not node or not vm_type:
            await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
            return

        resource = getattr(proxmox.nodes(node), vm_type)(vmid)
        await run_proxmox_async(resource.status.start.post)
        await interaction.followup.send(f'▶️ VMID: {vmid} を起動しました。')
    except Exception as e:
        await interaction.followup.send(f'❌ 起動失敗: {e}')

# 6. 再起動 (/reboot)
@bot.tree.command(name="reboot", description="VMを再起動")
@app_commands.autocomplete(vmid=vmid_autocomplete)
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
        node, vm_type = await get_device_node_and_type(vmid)
        if not node or not vm_type:
            await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
            return

        resource = getattr(proxmox.nodes(node), vm_type)(vmid)
        await run_proxmox_async(resource.status.reboot.post)
        await interaction.followup.send(f'🔄 VMID: {vmid} を再起動中...')
    except Exception as e:
        await interaction.followup.send(f'❌ 再起動失敗: {e}')

# 7. 削除 (/delete)
@bot.tree.command(name="delete", description="VMを削除 (警告: データ消失)")
@app_commands.autocomplete(vmid=vmid_autocomplete)
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
        node, vm_type = await get_device_node_and_type(vmid)
        if not node or not vm_type:
            await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
            return

        resource = getattr(proxmox.nodes(node), vm_type)(vmid)
        try:
            await run_proxmox_async(resource.status.stop.post)
            await asyncio.sleep(2)
        except:
            pass
        await run_proxmox_async(resource.delete)
        await interaction.followup.send(f'🗑️ **削除完了**: VMID {vmid} を削除しました。')
    except Exception as e:
        await interaction.followup.send(f'❌ 削除失敗: {e}')


# 8. スナップショット管理 (/snapshot)
snapshot_group = app_commands.Group(name="snapshot", description="スナップショットの管理")

@snapshot_group.command(name="create", description="スナップショットを作成")
@app_commands.describe(vmid="対象のVMID", name="スナップショット名")
@app_commands.autocomplete(vmid=vmid_autocomplete)
async def snapshot_create(interaction: discord.Interaction, vmid: int, name: str):
    """
    Creates a new snapshot for a specific VM.
    特定のVMのスナップショットを作成します。
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
        await run_proxmox_async(resource.snapshot.post, snapname=name)
        await interaction.followup.send(f'📸 **スナップショット作成**: {name} (VMID: {vmid})')
    except Exception as e:
        await interaction.followup.send(f'❌ 作成失敗: {e}')

@snapshot_group.command(name="list", description="スナップショット一覧を表示")
@app_commands.describe(vmid="対象のVMID")
@app_commands.autocomplete(vmid=vmid_autocomplete)
async def snapshot_list(interaction: discord.Interaction, vmid: int):
    """
    Lists all snapshots for a specific VM.
    特定のVMのスナップショットを一覧表示します。
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
        snapshots = await run_proxmox_async(resource.snapshot.get)

        embed = discord.Embed(title=f"📸 Snapshots: VMID {vmid}", color=discord.Color.blue())
        desc = []
        for snap in snapshots:
            snap_name = snap.get('name')
            snap_time = snap.get('snaptime', 'Unknown') # Timestamp
            desc.append(f"• **{snap_name}**")

        if not desc:
            desc.append("スナップショットはありません。")

        embed.description = "\n".join(desc)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f'❌ 取得失敗: {e}')

class SnapshotRollbackView(discord.ui.View):
    def __init__(self, resource, snapname):
        super().__init__(timeout=60)
        self.resource = resource
        self.snapname = snapname
        self.value = None

    @discord.ui.button(label="Confirm Rollback", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            await run_proxmox_async(self.resource.snapshot(self.snapname).rollback.post)
            await interaction.followup.send(f'✅ **ロールバック完了**: {self.snapname}')
            self.value = True
            self.stop()
        except Exception as e:
            await interaction.followup.send(f'❌ ロールバック失敗: {e}')

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message('キャンセルしました。', ephemeral=True)
        self.value = False
        self.stop()

@snapshot_group.command(name="rollback", description="スナップショットへロールバック (要確認)")
@app_commands.describe(vmid="対象のVMID", name="スナップショット名")
@app_commands.autocomplete(vmid=vmid_autocomplete)
async def snapshot_rollback(interaction: discord.Interaction, vmid: int, name: str):
    """
    Rolls back to a specific snapshot.
    特定のスナップショットにロールバックします。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True) # Confirmation should be private or explicit
    try:
        node, vm_type = await get_device_node_and_type(vmid)
        if not node or not vm_type:
            await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
            return

        resource = getattr(proxmox.nodes(node), vm_type)(vmid)

        # Check if snapshot exists
        snapshots = await run_proxmox_async(resource.snapshot.get)
        if not any(s.get('name') == name for s in snapshots):
             await interaction.followup.send(f'❌ スナップショット `{name}` が見つかりません。')
             return

        view = SnapshotRollbackView(resource, name)
        await interaction.followup.send(f"⚠️ **警告**: VMID {vmid} をスナップショット `{name}` にロールバックしますか？\n現在の状態は失われます。", view=view)

    except Exception as e:
        await interaction.followup.send(f'❌ エラー: {e}')

bot.tree.add_command(snapshot_group)

# 9. 監視設定管理 (/monitor)
monitor_group = app_commands.Group(name="monitor", description="監視対象の管理")

@monitor_group.command(name="add", description="監視対象に追加")
@app_commands.describe(vmid="対象のVMID")
@app_commands.autocomplete(vmid=vmid_autocomplete)
async def monitor_add(interaction: discord.Interaction, vmid: int):
    """
    Adds a VMID to the monitoring list.
    監視リストにVMIDを追加します。
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
async def monitor_remove(interaction: discord.Interaction, vmid: int):
    """
    Removes a VMID from the monitoring list.
    監視リストからVMIDを削除します。
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
async def monitor_list_cmd(interaction: discord.Interaction):
    """
    Lists all monitored VMIDs.
    監視対象のVMID一覧を表示します。
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

bot.tree.add_command(monitor_group)

# 10. Advanced Power Management
@bot.tree.command(name="shutdown", description="ACPIシャットダウン (安全な停止)")
@app_commands.describe(vmid="対象のVMID")
@app_commands.autocomplete(vmid=vmid_autocomplete)
async def shutdown(interaction: discord.Interaction, vmid: int):
    """
    Sends an ACPI shutdown signal to the VM.
    VMにACPIシャットダウン信号を送信します。
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
        await run_proxmox_async(resource.status.shutdown.post)
        await interaction.followup.send(f'🛑 **シャットダウン信号送信**: VMID {vmid}')
    except Exception as e:
        await interaction.followup.send(f'❌ 失敗: {e}')

@bot.tree.command(name="stop", description="強制停止 (電源オフ)")
@app_commands.describe(vmid="対象のVMID")
@app_commands.autocomplete(vmid=vmid_autocomplete)
async def stop(interaction: discord.Interaction, vmid: int):
    """
    Forcefully stops the VM.
    VMを強制停止します。
    """
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    # Confirmation needed
    view = discord.ui.View()

    async def confirm_callback(interaction: discord.Interaction):
        await interaction.response.defer()
        try:
             node, vm_type = await get_device_node_and_type(vmid)
             if not node or not vm_type:
                 await interaction.followup.send(f'❌ VMID {vmid} が見つかりません。')
                 return

             resource = getattr(proxmox.nodes(node), vm_type)(vmid)
             await run_proxmox_async(resource.status.stop.post)
             await interaction.followup.send(f'⚡ **強制停止完了**: VMID {vmid}')
        except Exception as e:
             await interaction.followup.send(f'❌ 失敗: {e}')

    async def cancel_callback(interaction: discord.Interaction):
        await interaction.response.send_message('キャンセルしました。', ephemeral=True)

    confirm_btn = discord.ui.Button(label="Confirm Force Stop", style=discord.ButtonStyle.red)
    confirm_btn.callback = confirm_callback

    cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.grey)
    cancel_btn.callback = cancel_callback

    view.add_item(confirm_btn)
    view.add_item(cancel_btn)

    await interaction.response.send_message(f"⚠️ **警告**: VMID {vmid} を強制停止しますか？\n保存されていないデータは失われる可能性があります。", view=view, ephemeral=True)

bot.run(config.DISCORD_TOKEN)
