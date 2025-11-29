import discord
from discord.ext import commands
import config
import os

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

        This method loads extensions from the `cogs` directory and syncs the slash commands.
        このメソッドは、`cogs` ディレクトリから拡張機能を読み込み、スラッシュコマンドを同期します。
        """
        # Load extensions
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                await self.load_extension(f'cogs.{filename[:-3]}')
                print(f"Loaded extension: {filename[:-3]}")

        # config.GUILD_ID を使用
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("Slash commands synced!")

if __name__ == '__main__':
    bot = ProxmoxBot()
    bot.run(config.DISCORD_TOKEN)
