import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import config
from utils.api import proxmox, run_proxmox_async, get_device_node_and_type, check_access, vmid_autocomplete

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

class ManagementCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create", description="テンプレートからVMを作成")
    @app_commands.describe(template_id="クローン元VMID", new_vmid="新VMID", name="新VM名")
    @app_commands.autocomplete(template_id=vmid_autocomplete)
    async def create(self, interaction: discord.Interaction, template_id: int, new_vmid: int, name: str):
        """
        Creates a new VM by cloning an existing template.
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

    @app_commands.command(name="resize", description="スペック変更 (再起動後反映)")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def resize(self, interaction: discord.Interaction, vmid: int, cores: int, memory_mb: int):
        """
        Updates the CPU cores and memory allocation for a specific VM.
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

    @app_commands.command(name="start", description="VMを起動")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def start(self, interaction: discord.Interaction, vmid: int):
        """
        Starts a Virtual Machine.
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

    @app_commands.command(name="reboot", description="VMを再起動")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def reboot(self, interaction: discord.Interaction, vmid: int):
        """
        Reboots a Virtual Machine.
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

    @app_commands.command(name="shutdown", description="ACPIシャットダウン (安全な停止)")
    @app_commands.describe(vmid="対象のVMID")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def shutdown(self, interaction: discord.Interaction, vmid: int):
        """
        Sends an ACPI shutdown signal to the VM.
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

    @app_commands.command(name="stop", description="強制停止 (電源オフ)")
    @app_commands.describe(vmid="対象のVMID")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def stop(self, interaction: discord.Interaction, vmid: int):
        """
        Forcefully stops the VM.
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

    @app_commands.command(name="delete", description="VMを削除 (警告: データ消失)")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def delete(self, interaction: discord.Interaction, vmid: int):
        """
        Deletes a Virtual Machine.
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

    # Snapshot Group
    snapshot_group = app_commands.Group(name="snapshot", description="スナップショットの管理")

    @snapshot_group.command(name="create", description="スナップショットを作成")
    @app_commands.describe(vmid="対象のVMID", name="スナップショット名")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def snapshot_create(self, interaction: discord.Interaction, vmid: int, name: str):
        """
        Creates a new snapshot for a specific VM.
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
    async def snapshot_list(self, interaction: discord.Interaction, vmid: int):
        """
        Lists all snapshots for a specific VM.
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
                desc.append(f"• **{snap_name}**")

            if not desc:
                desc.append("スナップショットはありません。")

            embed.description = "\n".join(desc)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f'❌ 取得失敗: {e}')

    @snapshot_group.command(name="rollback", description="スナップショットへロールバック (要確認)")
    @app_commands.describe(vmid="対象のVMID", name="スナップショット名")
    @app_commands.autocomplete(vmid=vmid_autocomplete)
    async def snapshot_rollback(self, interaction: discord.Interaction, vmid: int, name: str):
        """
        Rolls back to a specific snapshot.
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

async def setup(bot):
    await bot.add_cog(ManagementCommands(bot))
