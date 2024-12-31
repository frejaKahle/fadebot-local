import discord
from discord.ext import commands
from private.cfg import fadebot_token
from cfg import  usr_cfg
from typing import Self, Optional

class FadeBot(commands.Bot):
    def __init__(self, command_prefix, *, help_command = ..., tree_cls = commands.app_commands.CommandTree, description = None, allowed_contexts = ..., allowed_installs = ..., intents, **options):
        self.__voice_client: Optional[discord.VoiceClient] = None
        super().__init__(command_prefix, help_command=help_command, tree_cls=tree_cls, description=description, allowed_contexts=allowed_contexts, allowed_installs=allowed_installs, intents=intents, **options)
    @Self.command(name = 'savelocation', help ='Saves the voice channel you are in to the config file')
    async def save_location(ctx: commands.Context):
        if ctx.author.voice: update = {
            'Guild_ID': ctx.guild.id,
            'Voice_Channel_ID': ctx.author.voice.channel.id
        }
        else: update = {'Guild_ID': ctx.guild.id}
        usr_cfg.update(update)
    def call_async_method(self,method: callable, *args, **kwargs):
        self.loop.create_task(method(*args,**kwargs))
    async def join_voice(self) -> bool:
        cfg = usr_cfg.get()['discord']
        if 'Voice_Channel_ID' in cfg: vc = self.get_channel(int(cfg['Voice_Channel_ID']))
        else:
            print(f"No saved voice channel: please run command '{self.command_prefix}savelocation' while connected to a voice channel to save")
            return False
        if self.__voice_client == None: self.__voice_client = await vc.connect()
        else: await self.__voice_client.move_to(vc)
        return True
    async def play_audio(self, audio_source: discord.AudioSource):
        if self.__voice_client == None and not await self.join_voice(): return
        self.__voice_client.play(audio_source)
    def stop_audio(self):
        if self.__voice_client != None and self.__voice_client.is_playing(): self.__voice_client.stop()


def generate_bot() -> FadeBot:
    intents = discord.Intents().all()
    bot = FadeBot("X!", intents=intents)
    bot.run(token=fadebot_token)

    
    
    