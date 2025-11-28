import discord
from discord.ext import commands
import config
import os
import asyncio

class ProxmoxBot(commands.Bot):
    """
    A custom Discord Bot class that manages Proxmox Virtual Machines.
    """
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        """
        Loads extensions and syncs commands.
        """
        # Load extensions
        initial_extensions = ['cogs.basic', 'cogs.management', 'cogs.monitoring']
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                print(f"Loaded extension: {extension}")
            except Exception as e:
                print(f"Failed to load extension {extension}: {e}")

        # Sync commands
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("Slash commands synced!")

bot = ProxmoxBot()

if __name__ == '__main__':
    bot.run(config.DISCORD_TOKEN)
