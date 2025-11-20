import discord
from discord import app_commands
from discord.ext import commands, tasks
from proxmoxer import ProxmoxAPI
import urllib3
import asyncio
import os
from datetime import timedelta
from dotenv import load_dotenv

# --- 設定読み込み ---
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID'))
ALLOWED_CATEGORY_ID = int(os.getenv('ALLOWED_CATEGORY_ID'))
ALERT_CHANNEL_ID = int(os.getenv('ALERT_CHANNEL_ID'))

PROXMOX_HOST = os.getenv('PROXMOX_HOST')
PROXMOX_USER = os.getenv('PROXMOX_USER')
PROXMOX_TOKEN_NAME = os.getenv('PROXMOX_TOKEN_NAME')
PROXMOX_TOKEN_VALUE = os.getenv('PROXMOX_TOKEN_VALUE')
NODE_NAME = os.getenv('NODE_NAME')

# 監視対象VMリスト
MONITOR_VM_IDS = [100, 101, 105]

# SSL警告無視
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Proxmox API ---
proxmox = ProxmoxAPI(
    PROXMOX_HOST, user=PROXMOX_USER, 
    token_name=PROXMOX_TOKEN_NAME, token_value=PROXMOX_TOKEN_VALUE,
    verify_ssl=False
)

# --- Bot Class定義 ---
class ProxmoxBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("Slash commands synced!")
        
        if not self.monitor_vms.is_running():
            self.monitor_vms.start()

    @tasks.loop(minutes=1)
    async def monitor_vms(self):
        channel = self.get_channel(ALERT_CHANNEL_ID)
        if not channel: return

        for vmid in MONITOR_VM_IDS:
            try:
                status_data = proxmox.nodes(NODE_NAME).qemu(vmid).status.current.get()
                if status_data.get('status') == 'stopped':
                    await channel.send(f'🚨 **緊急**: VMID {vmid} ({status_data.get("name")}) が停止しています！')
            except Exception as e:
                print(f"Monitor Error {vmid}: {e}")

    @monitor_vms.before_loop
    async def before_monitor(self):
        await self.wait_until_ready()

bot = ProxmoxBot()

# --- 共通チェック関数 (カテゴリのみチェック) ---
def check_access(interaction: discord.Interaction) -> str | None:
    # カテゴリIDを取得。ない場合はNone
    category_id = getattr(interaction.channel, 'category_id', None)
    
    if category_id != ALLOWED_CATEGORY_ID:
        return "❌ このコマンドは指定された管理カテゴリ内のチャンネルでのみ使用可能です。"
    return None

# --- コマンド定義 ---

# 1. 一覧表示 (/list)
@bot.tree.command(name="list", description="VMの一覧とステータスを表示")
async def list_vms(interaction: discord.Interaction):
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        # 全VM取得
        vms = proxmox.nodes(NODE_NAME).qemu.get()
        # VMID順にソート
        vms.sort(key=lambda x: int(x['vmid']))

        # Embed作成
        embed = discord.Embed(title="📦 Proxmox VM List", color=discord.Color.blue())
        
        description_lines = []
        for vm in vms:
            status = vm.get('status')
            icon = "🟢" if status == 'running' else "🔴"
            vmid = vm.get('vmid')
            name = vm.get('name')
            # フォーマット: 🟢 100: MyServer
            description_lines.append(f"{icon} **{vmid}**: {name}")

        # リストが長すぎる場合の対策（2000文字制限対策として分割するか、今回はシンプルに結合）
        embed.description = "\n".join(description_lines)
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f'❌ 取得失敗: {e}')

# 2. 詳細情報 (/info)
@bot.tree.command(name="info", description="VMの詳細スペックと稼働状況を確認")
@app_commands.describe(vmid="対象のVMID")
async def info(interaction: discord.Interaction, vmid: int):
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        # 現在の動的ステータス (CPU負荷, Uptimeなど)
        status = proxmox.nodes(NODE_NAME).qemu(vmid).status.current.get()
        # 静的な設定情報 (割り当てコア数, メモリ設定など)
        config = proxmox.nodes(NODE_NAME).qemu(vmid).config.get()

        vm_name = status.get('name', 'Unknown')
        vm_status = status.get('status', 'unknown')
        
        # Embedの色決定
        color = discord.Color.green() if vm_status == 'running' else discord.Color.red()

        embed = discord.Embed(title=f"ℹ️ VM Info: {vm_name}", color=color)
        embed.add_field(name="VMID", value=str(vmid), inline=True)
        embed.add_field(name="Status", value=vm_status.upper(), inline=True)
        
        # CPU情報
        cores = config.get('cores', '?')
        cpu_usage = status.get('cpu', 0) * 100
        embed.add_field(name="CPU", value=f"{cores} Cores\nUsage: {cpu_usage:.1f}%", inline=True)

        # メモリ情報 (バイト→MB変換)
        max_mem = int(status.get('maxmem', 0)) / 1024 / 1024
        cur_mem = int(status.get('mem', 0)) / 1024 / 1024
        embed.add_field(name="Memory", value=f"{cur_mem:.0f}MB / {max_mem:.0f}MB", inline=True)

        # 稼働時間
        uptime_sec = int(status.get('uptime', 0))
        uptime_str = str(timedelta(seconds=uptime_sec))
        embed.add_field(name="Uptime", value=uptime_str, inline=True)

        # ネットワーク (QEMU Guest Agentが入っている場合のみIPが取れる場合があるが、APIからの取得は工夫が必要)
        # ここでは簡易的にconfigのnet0設定を表示
        net0 = config.get('net0', 'N/A')
        embed.add_field(name="Network (net0)", value=f"`{net0}`", inline=False)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f'❌ 情報取得失敗: {e}')

# 3. VM作成 (/create)
@bot.tree.command(name="create", description="テンプレートからVMを作成")
@app_commands.describe(template_id="クローン元VMID", new_vmid="新VMID", name="新VM名")
async def create(interaction: discord.Interaction, template_id: int, new_vmid: int, name: str):
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(NODE_NAME).qemu(template_id).clone.post(
            newid=new_vmid, name=name, full=1
        )
        await interaction.followup.send(
            f'✅ **作成完了**: `{name}` (ID: {new_vmid})\n'
            f'Cloud-Init設定により起動後にTailscaleへ接続されます。\n'
            f'コマンド: `/start vmid:{new_vmid}`'
        )
    except Exception as e:
        await interaction.followup.send(f'❌ 作成失敗: {e}')

# 4. リソース変更 (/resize)
@bot.tree.command(name="resize", description="スペック変更 (再起動後反映)")
async def resize(interaction: discord.Interaction, vmid: int, cores: int, memory_mb: int):
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(NODE_NAME).qemu(vmid).config.post(cores=cores, memory=memory_mb)
        await interaction.followup.send(f'⚙️ **設定変更**: VMID {vmid} → {cores} Cores, {memory_mb} MB\n⚠️ 再起動後に適用されます。')
    except Exception as e:
        await interaction.followup.send(f'❌ 変更失敗: {e}')

# 5. 起動 (/start)
@bot.tree.command(name="start", description="VMを起動")
async def start(interaction: discord.Interaction, vmid: int):
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(NODE_NAME).qemu(vmid).status.start.post()
        await interaction.followup.send(f'▶️ VMID: {vmid} を起動しました。')
    except Exception as e:
        await interaction.followup.send(f'❌ 起動失敗: {e}')

# 6. 再起動 (/reboot)
@bot.tree.command(name="reboot", description="VMを再起動")
async def reboot(interaction: discord.Interaction, vmid: int):
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        proxmox.nodes(NODE_NAME).qemu(vmid).status.reboot.post()
        await interaction.followup.send(f'🔄 VMID: {vmid} を再起動中...')
    except Exception as e:
        await interaction.followup.send(f'❌ 再起動失敗: {e}')

# 7. 削除 (/delete)
@bot.tree.command(name="delete", description="VMを削除 (警告: データ消失)")
async def delete(interaction: discord.Interaction, vmid: int):
    if error := check_access(interaction):
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.defer()
    try:
        try:
            proxmox.nodes(NODE_NAME).qemu(vmid).status.stop.post()
            await asyncio.sleep(2)
        except:
            pass
        proxmox.nodes(NODE_NAME).qemu(vmid).delete()
        await interaction.followup.send(f'🗑️ **削除完了**: VMID {vmid} を削除しました。')
    except Exception as e:
        await interaction.followup.send(f'❌ 削除失敗: {e}')

bot.run(DISCORD_TOKEN)