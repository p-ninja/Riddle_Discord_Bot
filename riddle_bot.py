from discord import Client
import os


class Bot(Client):
    async def on_ready(self):
        print(f"Logged in as {self.user}")


Bot().run(os.environ["TOKEN"])
