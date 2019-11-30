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
PREFIX = config["prefix"]


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


def category_name(category_id, category, escaped=False):
    if escaped:
        return fr"\[{category_id}\] {category} - Levels"
    else:
        return f"[{category_id}] {category} - Levels"


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
            match = re.match("^" + category_name(r"(\d+)", "(.*)", escaped=True) + "$", category.name)
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
        _, _, category_channel, _, _ = self.get_category(name=category)
        if category_channel is None:
            return None, None, None

        level_channel: Optional[TextChannel] = utils.get(category_channel.channels, name=level_name(level_id))
        solution_channel: Optional[TextChannel] = utils.get(category_channel.channels, name=solution_name(level_id))
        role: Optional[Role] = utils.get(self.guild.roles, name=role_name(category, level_id))
        return level_channel, solution_channel, role

    def get_category(self, *, name=None, category_id=None):
        assert name is not None or category_id is not None
        category_channel: Optional[CategoryChannel] = None

        regex_id = str(category_id or r"\d+")
        regex_name = name or ".*"
        for cat in self.guild.categories:
            match = re.match("^" + category_name(f"({regex_id})", f"({regex_name})", escaped=True) + "$", cat.name)
            if match:
                category_id, name = match.groups()
                category_id = int(category_id)
                category_channel = cat
        riddle_master_role: Optional[Role] = utils.get(self.guild.roles, name=riddle_master_name(name))
        leaderboard_channel: Optional[TextChannel] = category_channel and utils.get(
            category_channel.channels, name="leaderboard"
        )
        return category_id, name, category_channel, riddle_master_role, leaderboard_channel

    async def on_member_join(self, member: Member):
        if member.guild.id != self.guild.id:
            return

        await member.send(open("texts/welcome_dm.txt").read().format(user=member.mention))

        for _, cat_name in self.get_categories():
            _, _, role = self.get_level(cat_name, 1)
            if role is not None:
                await member.add_roles(role)
            else:
                _, _, _, riddle_master_role, _ = self.get_category(name=cat_name)
                await member.add_roles(riddle_master_role)
            await self.update_leaderboard(cat_name)

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

    async def update_leaderboard(self, category):
        _, _, _, riddle_master_role, leaderboard_channel = self.get_category(name=category)
        async for message in leaderboard_channel.history():
            if message.author == self.user:
                break
        else:
            message = await leaderboard_channel.send(embed=create_embed())

        level_count = self.get_level_count(category)

        leaderboard = []
        for member in self.guild.members:
            if await self.is_authorized(member):
                continue

            for role in member.roles:
                match = re.match("^" + role_name(category, r"(\d+)") + "$", role.name)
                if role.id == riddle_master_role.id:
                    leaderboard.append((level_count, f"@{member}"))
                elif match:
                    leaderboard.append((int(match.group(1)) - 1, f"@{member}"))
        leaderboard.sort(reverse=True)
        max_width = max((len(member) for _, member in leaderboard), default=0)
        description = ["```", "MEMBER".ljust(max_width) + "    SCORE"]
        for score, member in leaderboard[:20]:
            description.append(member.ljust(max_width) + f"    {score}")
        description.append("```")

        embed = create_embed(title="Leaderboard", description="\n".join(description))

        await message.edit(embed=embed)

    async def on_message(self, message: Message):
        if message.author == self.user:
            return

        if message.content.startswith(PREFIX):
            cmd, *args = message.content[1:].split()
            if cmd == "add":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                if len(args) < 2 or args[0] not in ("category", "level"):
                    await message.channel.send(f"usage: {PREFIX}add category|level <category>")
                    return
                category = " ".join(args[1:])
                if args[0] == "level":
                    _, cat_name, category_channel, _, _ = self.get_category(category_id=category)
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
                        embed=(
                            create_embed(
                                title=f"[{category}] {cat_name} - Level {level_id}", description=riddle.content
                            )
                        )
                    )
                    await message.channel.send("Riddle has been created! :+1:")
                    await message.channel.send(f"Now go to {solution_channel.mention} and send the solution.")
                    await message.channel.send(
                        f"After that type `{PREFIX}notify {category} {level_id}` to notify the Riddle Masters :wink:"
                    )
                else:
                    category_channel: CategoryChannel = await self.guild.create_category(
                        category_name(self.get_next_category_id(), category)
                    )
                    await category_channel.create_text_channel(
                        "leaderboard",
                        overwrites={
                            self.guild.default_role: PermissionOverwrite(read_messages=True, send_messages=False),
                            self.guild.me: PermissionOverwrite(read_messages=True, send_messages=True),
                        },
                    )

                    riddle_master_role: Role = await self.guild.create_role(
                        name=riddle_master_name(category), color=Color(random.randint(0, 0xFFFFFF)), hoist=True
                    )
                    for member in self.guild.members:
                        if member.id != self.user.id:
                            await member.add_roles(riddle_master_role)
                    await self.update_leaderboard(category)
                    await message.channel.send("Category has been created!")
            elif cmd == "notify":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                if len(args) != 2:
                    await message.channel.send(f"usage: {PREFIX}notify <category-id> <level-id>")
                    return
                else:
                    if not args[-1].isnumeric():
                        await message.channel.send("Level ID has to be numeric!")
                        return
                    category = args[0]
                    level_id = int(args[1])

                _, cat_name, _, riddle_master_role, _ = self.get_category(category_id=category)
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
                await self.update_leaderboard(cat_name)
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
                        f"usage: {PREFIX}delete category <category-id>\n"
                        f"   or: {PREFIX}delete level[s] <category-id> <level-id> [<level-id>]"
                    )
                    return

                category = args[1]
                _, cat_name, category_channel, riddle_master_role, leaderboard = self.get_category(category_id=category)
                if args[0] == "category":
                    for level in self.get_levels(cat_name):
                        level_channel, solution_channel, role = self.get_level(cat_name, level)
                        if level_channel:
                            await level_channel.delete()
                        if solution_channel:
                            await solution_channel.delete()
                        if role:
                            await role.delete()
                    if leaderboard:
                        await leaderboard.delete()
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
                        await level_channel.edit(name=level_name(level - (to_level_id - from_level_id + 1)))
                        await solution_channel.edit(name=solution_name(level - (to_level_id - from_level_id + 1)))
                        await role.edit(name=role_name(cat_name, level - (to_level_id - from_level_id + 1)))
                    await self.update_leaderboard(cat_name)

                await message.channel.send("Done")
            elif cmd == "info":
                embed = create_embed(title="Info")
                for cat_id, cat_name in self.get_categories():
                    count = self.get_level_count(cat_name)
                    embed.add_field(
                        name=f"[{cat_id}] {cat_name}", value=f"{count} Level" + "s" * (count != 1), inline=False
                    )
                await message.channel.send(embed=embed)
            elif cmd == "setup":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                self.settings_message = await self.settings_channel.send(
                    embed=create_embed(title="Settings", description=open("texts/settings.txt").read())
                )
                await self.settings_message.add_reaction(BELL)
            elif cmd in ("solve", "lösen"):
                if not isinstance(message.channel, DMChannel):
                    await message.delete()
                    await message.channel.send(
                        f"Hey, {message.author.mention}! Schick mir deine Lösung bitte privat :wink:"
                    )
                    return

                if not args:
                    await message.channel.send(f"usage: {PREFIX}solve <category-id>")
                    return

                category = " ".join(args)
                _, cat_name, _, riddle_master_role, _ = self.get_category(category_id=category)
                if riddle_master_role is None:
                    await message.channel.send("Tut mir leid, diese Kategorie kenne ich nicht :shrug:")
                    return

                member: Member = self.guild.get_member(message.author.id)
                for role in member.roles:
                    if role.id == riddle_master_role.id:
                        await message.channel.send("Hey, du hast bereits alle Rätsel in dieser Kategorie gelöst :wink:")
                        return

                    if re.match("^" + role_name(cat_name, r"(\d+)") + "$", role.name):
                        level_id = int(re.match("^" + role_name(cat_name, r"(\d+)") + "$", role.name).group(1))
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
                    if re.match(f"^{msg.content.lower()}$", answer.lower()):
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
                await self.update_leaderboard(cat_name)
            elif cmd == "fix":
                await self.fix_member(self.guild.get_member(message.author.id))
                for _, cat_name in self.get_categories():
                    await self.update_leaderboard(cat_name)
                await message.channel.send("Done")
            elif cmd == "fixall":
                if not await self.is_authorized(message.author):
                    await message.channel.send("You are not authorized to use this command!")
                    return

                for member in self.guild.members:
                    if member != self.user:
                        await self.fix_member(member)
                for _, cat_name in self.get_categories():
                    await self.update_leaderboard(cat_name)
                await message.channel.send("Done")
            elif cmd == "score":
                member: Member = self.guild.get_member(message.author.id)
                embed = create_embed(title=f"Score of @{member}")
                total = 0
                for _, cat_name in self.get_categories():
                    _, _, _, riddle_master_role, _ = self.get_category(name=cat_name)
                    level_count = self.get_level_count(cat_name)
                    for role in member.roles:
                        match = re.match("^" + role_name(cat_name, r"(\d+)") + "$", role.name)
                        points = None
                        if role.id == riddle_master_role.id:
                            points = level_count
                        elif match:
                            points = int(match.group(1)) - 1
                        if points is not None:
                            embed.add_field(name=cat_name, value=f"{points} Points", inline=False)
                            total += points
                            break
                embed.add_field(name="TOTAL", value=f"{total} Points", inline=False)
                await message.channel.send(embed=embed)
            elif cmd == "help":
                response = "```\n"
                if await self.is_authorized(message.author):
                    response += open("texts/admin_commands.txt").read().format(prefix=PREFIX) + "\n"
                response += open("texts/user_commands.txt").read().format(prefix=PREFIX) + "\n```"
                await message.channel.send(response)
            else:
                await message.channel.send(f"Unknown command! Type `{PREFIX}help` to get a list of commands!")

    async def fix_member(self, member: Member):
        for cat_id, cat_name in self.get_categories():
            _, _, _, riddle_master_role, _ = self.get_category(category_id=cat_id)

            for role in member.roles:
                if role.id == riddle_master_role.id:
                    break
                elif re.match("^" + role_name(cat_name, r"(\d+)") + "$", role.name):
                    break
            else:
                _, _, role = self.get_level(cat_name, 1)
                await member.add_roles(role or riddle_master_role)


Bot().run(os.environ["TOKEN"])
