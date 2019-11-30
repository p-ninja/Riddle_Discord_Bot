import asyncio
import json
import os
import random
import re
from typing import Optional, List, Tuple

from discord import (
    Client,
    Message,
    Member,
    Guild,
    CategoryChannel,
    utils,
    Embed,
    Role,
    PermissionOverwrite,
    User,
    DMChannel,
    Color,
)
from discord import TextChannel

BELL = "🔔"

config: dict = json.load(open("config.json"))
GUILD: int = config["guild"]
NOTIFICATION_ROLE: int = config["notification_role"]
SETTINGS_CHANNEL: int = config["settings_channel"]


def create_embed(**kwargs):
    embed = Embed(**kwargs)
    embed.set_footer(text="Bot by @Defelo#2022")
    return embed


def level_name(level_id):
    return f"level-{level_id}"


def solution_name(level_id):
    return f"solution-{level_id}"


def role_name(category, level_id):
    return f"{category} - Level {level_id}"


def riddle_master_name(category):
    return f"Master of {category}"


def category_name(category_id, category):
    return f"{category_id} - {category} - Levels"


class Bot(Client):
    def __init__(self):
        super().__init__()

        self.guild: Optional[Guild] = None
        self.notification_role: Optional[Role] = None
        self.settings_channel: Optional[TextChannel] = None
        self.settings_message: Optional[Message] = None

    async def on_ready(self):
        print(f"Logged in as {self.user}")

        self.guild: Guild = self.get_guild(GUILD)
        self.notification_role: Role = self.guild.get_role(NOTIFICATION_ROLE)
        self.settings_channel: TextChannel = self.guild.get_channel(SETTINGS_CHANNEL)
        async for msg in self.settings_channel.history():
            self.settings_message: Message = msg
            break

    def get_levels(self, category: str) -> List[int]:
        out = []
        for role in self.guild.roles:
            match = re.match("^" + role_name(category, r"(\d+)") + "$", role.name)
            if match:
                out.append(int(match.group(1)))
        return sorted(out)

    def get_categories(self) -> List[Tuple[int, str]]:
        out = []
        for category in self.guild.categories:
            match = re.match("^" + category_name(r"(\d+)", "(.*)") + "$", category.name)
            if match:
                category_id, name = match.groups()
                out.append((int(category_id), name))
        return out

    def get_next_category_id(self) -> int:
        return max((cat_id for cat_id, _ in self.get_categories()), default=0) + 1

    def get_max_level_id(self, category: str) -> int:
        return max(self.get_levels(category), default=0)

    def get_level_count(self, category: str) -> int:
        return len(self.get_levels(category))

    async def is_authorized(self, user: User) -> bool:
        member: Optional[Member] = self.guild.get_member(user.id)
        return member and member.guild_permissions.administrator

    def get_level(self, category, level_id):
        _, _, category_channel, _ = self.get_category(name=category)
        if category_channel is None:
            return None, None, None

        level_channel: Optional[TextChannel] = utils.get(category_channel.channels, name=level_name(level_id))
        solution_channel: Optional[TextChannel] = utils.get(category_channel.channels, name=solution_name(level_id))
        role: Optional[Role] = utils.get(self.guild.roles, name=role_name(category, level_id))
        return level_channel, solution_channel, role

    def get_category(self, *, name=None, category_id=None):
        assert name is not None or category_id is not None
        category_channel: Optional[CategoryChannel] = None
        for cat in self.guild.categories:
            match = re.match(
                "^" + category_name("(" + str(category_id or r"\d+") + ")", "(" + (name or ".*") + ")") + "$", cat.name
            )
            if match:
                category_id, name = match.groups()
                category_id = int(category_id)
                category_channel = cat
        riddle_master_role: Optional[Role] = utils.get(self.guild.roles, name=riddle_master_name(name))
        return category_id, name, category_channel, riddle_master_role

    async def on_member_join(self, member: Member):
        if member.guild.id != self.guild.id:
            return

        await member.send(open("texts/welcome_dm.txt").read().format(user=member.mention))

        for _, cat_name in self.get_categories():
            _, _, role = self.get_level(cat_name, 1)
            if role is not None:
                await member.add_roles(role)

    async def on_raw_reaction_add(self, payload):
        if self.settings_message is None or self.settings_message.id != payload.message_id:
            return
        if str(payload.emoji) != BELL or payload.user_id == self.user.id:
            return

        member: Message = self.guild.get_member(payload.user_id)
        await member.add_roles(self.notification_role)

    async def on_raw_reaction_remove(self, payload):
        if self.settings_message is None or self.settings_message.id != payload.message_id:
            return
        if str(payload.emoji) != BELL or payload.user_id == self.user.id:
            return

        member: Message = self.guild.get_member(payload.user_id)
        await member.remove_roles(self.notification_role)

    async def on_message(self, message: Message):
        if message.author == self.user:
            return

        if message.content.startswith("$"):
            cmd, *args = message.content[1:].split()
            if cmd == "add":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                if len(args) < 2 or args[0] not in ("category", "level"):
                    await message.channel.send("usage: $add category|level <category>")
                    return
                category = " ".join(args[1:])
                if args[0] == "level":
                    _, cat_name, category_channel, _ = self.get_category(category_id=category)
                    if category_channel is None:
                        await message.channel.send("Category does not exist!")
                        return

                    level_id = self.get_max_level_id(cat_name) + 1
                    await message.channel.send(f"Creating Level {level_id}")

                    role: Role = await self.guild.create_role(name=role_name(cat_name, level_id))

                    level_channel: TextChannel = await category_channel.create_text_channel(
                        level_name(level_id),
                        overwrites={
                            self.guild.default_role: PermissionOverwrite(read_messages=False),
                            role: PermissionOverwrite(read_messages=True, send_messages=False, add_reactions=False),
                            self.guild.me: PermissionOverwrite(read_messages=True, send_messages=True),
                        },
                    )
                    solution_channel: TextChannel = await category_channel.create_text_channel(
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
                    await message.channel.send("Now send me the riddle!")
                    riddle = await self.wait_for(
                        "message", check=lambda m: m.channel == message.channel and m.author == message.author
                    )
                    await level_channel.send(
                        embed=(create_embed(title=f"{cat_name} - Level {level_id}", description=riddle.content))
                    )
                    await message.channel.send("Riddle has been created! :+1:")
                    await message.channel.send(f"Now go to {solution_channel.mention} and send the solution.")
                    await message.channel.send(
                        f"After that type `$notify {category} {level_id}` to notify the Riddle Masters :wink:"
                    )
                else:
                    await self.guild.create_category(category_name(self.get_next_category_id(), category))
                    riddle_master_role: Role = await self.guild.create_role(
                        name=riddle_master_name(category), color=Color(random.randint(0, 0xFFFFFF))
                    )
                    for member in self.guild.members:
                        if member.id != self.user.id:
                            await member.add_roles(riddle_master_role)
                    await message.channel.send("Category has been created!")
            elif cmd == "notify":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                if len(args) != 2:
                    await message.channel.send("usage: $notify <category> <level-id>")
                    return
                else:
                    if not args[-1].isnumeric():
                        await message.channel.send("Level ID has to be numeric!")
                        return
                    category = args[0]
                    level_id = int(args[1])

                _, cat_name, _, riddle_master_role = self.get_category(category_id=category)
                level_channel, _, role = self.get_level(cat_name, level_id)
                notify_count = 0
                for member in self.guild.members:
                    if riddle_master_role in member.roles:
                        await member.remove_roles(riddle_master_role)
                        await member.add_roles(role)
                        if self.notification_role in member.roles:
                            await member.send(
                                "Hey! Es gibt jetzt ein neues Rätsel auf dem Riddle Server :wink:\n"
                                f"Schau mal hier: {level_channel.mention}"
                            )
                            notify_count += 1
                await message.channel.send(
                    f"{notify_count} member{[' has', 's have'][notify_count != 1]} been notified about the new level."
                )
            elif cmd == "delete":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                if not (
                    (len(args) == 2 and args[0] == "category")
                    or (len(args) == 3 and args[0] == "level")
                    or (len(args) == 4 and args[0] == "levels")
                ):
                    await message.channel.send(
                        "usage: $delete category <category>\n"
                        "   or: $delete level[s] <category> <level-id> [<level-id>]"
                    )
                    return

                category = args[1]
                _, cat_name, category_channel, riddle_master_role = self.get_category(category_id=category)
                if args[0] == "category":
                    for level in self.get_levels(cat_name):
                        level_channel, solution_channel, role = self.get_level(cat_name, level)
                        if level_channel:
                            await level_channel.delete()
                        if solution_channel:
                            await solution_channel.delete()
                        if role:
                            await role.delete()
                    if category_channel:
                        await category_channel.delete()
                    if riddle_master_role:
                        await riddle_master_role.delete()

                    await message.channel.send("Category has been deleted")
                else:
                    if args[0] == "level":
                        if not args[2].isnumeric():
                            await message.channel.send("Level ID has to be numeric!")
                            return
                        from_level_id = int(args[2])
                        to_level_id = from_level_id
                    else:
                        if (not args[2].isnumeric()) or (not args[3].isnumeric()):
                            await message.channel.send("Level ID has to be numeric!")
                            return
                        from_level_id = int(args[2])
                        to_level_id = int(args[3])

                    for level_id in range(from_level_id, to_level_id + 1):
                        level_channel, solution_channel, role = self.get_level(cat_name, level_id)
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
                    for level in self.get_levels(cat_name):
                        if level <= to_level_id:
                            continue
                        level_channel, solution_channel, role = self.get_level(cat_name, level)
                        level_count = to_level_id - from_level_id + 1
                        await level_channel.edit(name=level_name(level - level_count))
                        await solution_channel.edit(name=solution_name(level - level_count))
                        await role.edit(name=role_name(cat_name, level - level_count))

                await message.channel.send("Done")
            elif cmd == "info":
                embed = create_embed(title="Info")
                for _, cat_name in self.get_categories():
                    embed.add_field(name=cat_name, value=f"{self.get_level_count(cat_name)} Levels", inline=False)
                await message.channel.send(embed=embed)
            elif cmd == "setup":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                self.settings_message = await self.settings_channel.send(
                    embed=create_embed(title="Settings", description=open("texts/settings.txt").read())
                )
                await self.settings_message.add_reaction(BELL)
            elif cmd == "solve":
                if not isinstance(message.channel, DMChannel):
                    await message.delete()
                    await message.channel.send(
                        f"Hey, {message.author.mention}! Schick mir deine Lösung bitte privat :wink:"
                    )
                    return

                if not args:
                    await message.channel.send("usage: $solve <category>")
                    return

                category = " ".join(args)
                _, cat_name, _, riddle_master_role = self.get_category(category_id=category)
                if riddle_master_role is None:
                    await message.channel.send("Tut mir leid, diese Kategorie kenne ich nicht :shrug:")
                    return

                member: Member = self.guild.get_member(message.author.id)
                for role in member.roles:
                    if role.id == riddle_master_role.id:
                        await message.channel.send("Hey, du hast bereits alle Rätsel gelöst :wink:")
                        return

                    match = re.match("^" + role_name(cat_name, r"(\d+)") + "$", role.name)
                    if match:
                        level_id = int(match.group(1))
                        break
                else:
                    level_channel, _, role = self.get_level(cat_name, 1)
                    if role is not None:
                        await member.add_roles(role)
                        await message.channel.send(
                            "Sorry, du hattest anscheinend noch keine Level-Rolle.\n"
                            f"Schau jetzt mal in {level_channel.mention} :wink:"
                        )
                    return

                await message.channel.send("Ok, jetzt schick mir bitte die Lösung!")
                answer = (
                    await self.wait_for(
                        "message", check=lambda m: m.channel == message.channel and m.author == message.author
                    )
                ).content

                await message.channel.send("Hm, mal schauen, ob das richtig ist...")
                await asyncio.sleep(2)

                _, solution_channel, old_role = self.get_level(cat_name, level_id)
                async for msg in solution_channel.history():
                    if re.match(msg.content.lower(), answer.lower()):
                        level_channel, _, new_role = self.get_level(cat_name, level_id + 1)
                        await member.remove_roles(old_role)
                        if new_role is not None:
                            await member.add_roles(new_role)
                            await message.channel.send(f"Richtig! Du hast jetzt Zugriff auf {level_channel.mention}!")
                        else:
                            await member.add_roles(riddle_master_role)
                            await message.channel.send(f"Richtig! Leider war das aber schon das letzte Rätsel.")
                        break
                else:
                    await message.channel.send(f"Deine Antwort zu Level {level_id} ist leider falsch.")
            else:
                await message.channel.send("Unknown command!")


Bot().run(os.environ["TOKEN"])
