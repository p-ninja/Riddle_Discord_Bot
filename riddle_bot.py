import os
import re
from typing import Optional

from discord import Client, Message, Member, Guild, CategoryChannel, utils, Embed, Role, PermissionOverwrite, User
from discord import TextChannel


def level_name(level_id):
    return f"level-{level_id}"


def solution_name(level_id):
    return f"solution-{level_id}"


def role_name(level_id):
    return f"Level {level_id}"


class Bot(Client):
    def __init__(self):
        super().__init__()

        self.guild: Optional[Guild] = None
        self.level_category: Optional[CategoryChannel] = None
        self.solution_category: Optional[CategoryChannel] = None

    async def on_ready(self):
        print(f"Logged in as {self.user}")

        self.guild: Guild = self.get_guild(647130691842342913)
        self.level_category: CategoryChannel = self.guild.get_channel(648205081547767808)
        self.solution_category: CategoryChannel = self.guild.get_channel(647164872357838848)

    def get_levels(self):
        out = []
        for role in self.guild.roles:
            match = re.match("^" + role_name(r"(\d+)") + "$", role.name)
            if match:
                out.append(int(match.group(1)))
        return sorted(out)

    def get_max_level_id(self):
        return max(self.get_levels(), default=0)

    def get_level_count(self):
        return len(self.get_levels())

    async def is_authorized(self, user: User):
        member: Optional[Member] = self.guild.get_member(user.id)
        return member and member.guild_permissions.administrator

    def get_level(self, level_id):
        level_channel: Optional[TextChannel] = utils.get(self.level_category.channels, name=level_name(level_id))
        solution_channel: Optional[TextChannel] = utils.get(
            self.solution_category.channels, name=solution_name(level_id)
        )
        role: Optional[Role] = utils.get(self.guild.roles, name=role_name(level_id))
        return level_channel, solution_channel, role

    async def sort_roles(self):
        levels = self.get_levels()
        roles = [utils.get(self.guild.roles, name=role_name(level)) for level in levels]
        while True:
            all_ok = True
            for i in reversed(range(len(levels))):
                if roles[i].position != i + 1:
                    all_ok = False
                    await roles[i].edit(position=i + 1)
            if all_ok:
                break

    async def on_message(self, message: Message):
        if message.author == self.user:
            return

        if message.content.startswith("$"):
            cmd, *args = message.content[1:].split()
            if cmd == "stats":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                embed: Embed = Embed(title="Stats", color=0x008800)
                for level_id in self.get_levels():
                    level_channel, solution_channel, role = self.get_level(level_id)
                    status = f"Level Channel: {level_channel.mention}\n"
                    status += f"Solution Channel: {solution_channel and solution_channel.mention}\n"
                    if isinstance(message.channel, TextChannel):
                        status += f"Role: {role and role.mention}"
                    embed.add_field(name=f"Level {level_id}", value=status, inline=True)
                await message.channel.send(embed=embed)
            elif cmd == "add":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                level_id = self.get_max_level_id() + 1
                await message.channel.send(f"Creating Level {level_id}")

                role: Role = await self.guild.create_role(name=role_name(level_id), hoist=True)

                await self.sort_roles()

                level_channel: TextChannel = await self.level_category.create_text_channel(
                    level_name(level_id),
                    overwrites={
                        self.guild.default_role: PermissionOverwrite(read_messages=False),
                        role: PermissionOverwrite(read_messages=True, send_messages=False),
                    },
                )
                solution_channel: TextChannel = await self.solution_category.create_text_channel(
                    solution_name(level_id),
                    overwrites={
                        self.guild.default_role: PermissionOverwrite(read_messages=False),
                        self.guild.me: PermissionOverwrite(read_messages=True),
                    },
                )
                await message.channel.send(
                    f"Level {level_id} has been created.\n"
                    f"Level channel: {level_channel.mention}\n"
                    f"Solution channel: {solution_channel.mention}\n"
                    f"Role: {role.mention}"
                )
            elif cmd == "delete":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                if not args:
                    await message.channel.send("usage: $delete <level-id> [<level-id>]")
                    return
                else:
                    if (not args[0].isnumeric()) or (len(args) > 1 and not args[1].isnumeric()):
                        await message.channel.send("Level ID has to be numeric!")
                        return
                    from_level_id = int(args[0])
                    to_level_id = int(args[1]) if len(args) > 1 else from_level_id

                for level_id in range(from_level_id, to_level_id + 1):
                    level_channel, solution_channel, role = self.get_level(level_id)
                    existed = False
                    if level_channel:
                        await level_channel.delete()
                        existed = True
                    if solution_channel:
                        await solution_channel.delete()
                        existed = True
                    if role:
                        await role.delete()
                        existed = True

                    if existed:
                        await message.channel.send(f"Level {level_id} has been deleted")
                    else:
                        await message.channel.send(f"Level {level_id} does not exist")
                for level in self.get_levels():
                    if level <= to_level_id:
                        continue
                    level_channel, solution_channel, role = self.get_level(level)
                    level_count = to_level_id - from_level_id + 1
                    await level_channel.edit(name=level_name(level - level_count))
                    await solution_channel.edit(name=solution_name(level - level_count))
                    await role.edit(name=role_name(level - level_count))

                await message.channel.send("Done")

            elif cmd == "sort":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                async with message.channel.typing():
                    await self.sort_roles()
                    await message.channel.send("Roles have been sorted.")
            elif cmd == "info":
                await message.channel.send(f"{self.get_level_count()} Levels")


Bot().run(os.environ["TOKEN"])
