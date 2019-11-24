import os
import re
from typing import Optional

from discord import Client, Message, Member, Guild, CategoryChannel, utils, Embed, Role
from discord import TextChannel


class Bot(Client):
    def __init__(self):
        super().__init__()

        self.guild: Optional[Guild] = None
        self.level_category: Optional[CategoryChannel] = None
        self.solution_category: Optional[CategoryChannel] = None

    async def on_ready(self):
        print(f"Logged in as {self.user}")

        self.guild: Guild = self.get_guild(647130691842342913)
        self.level_category: CategoryChannel = utils.get(self.guild.categories, name="LEVELS")
        self.solution_category: CategoryChannel = utils.get(self.guild.categories, name="Lösungen")

    @staticmethod
    async def is_authorized(member: Member):
        return member.guild_permissions.administrator

    async def on_message(self, message: Message):
        if message.author == self.user:
            return

        if message.content.startswith("$"):
            cmd, *args = message.content[1:].split()
            if cmd == "stats":
                if not await Bot.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                embed: Embed = Embed(title="Stats", color=0x008800)
                for channel in self.level_category.channels:  # type: TextChannel
                    level_id: int = int(re.match(r"^lvl-(\d+)$", channel.name).group(1))
                    solution_channel: Optional[TextChannel] = utils.get(
                        self.solution_category.channels, name=f"lvl{level_id}"
                    )
                    role: Optional[Role] = utils.get(self.guild.roles, name=f"Level {level_id}")
                    status = f"Solution Channel: {solution_channel}\n"
                    status += f"Role: {role}"
                    embed.add_field(name=f"Level {level_id}", value=status, inline=False)
                await message.channel.send(embed=embed)


Bot().run(os.environ["TOKEN"])
