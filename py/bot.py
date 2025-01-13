import discord
from discord.ext import commands
from private.cfg import fadebot_token
from cfg import  bot_cfg
from typing import Optional
import threading

class FadeBot(commands.Bot):
    def __init__(self, command_prefix, **kwargs):  
        super().__init__(command_prefix, **kwargs)
        self.__voice_client: Optional[discord.VoiceClient] = None
        self.add_command(self.save_location)
        self.ready = threading.Event()
        self.__playing = False
    @commands.command(name = 'savelocation')
    async def save_location(self, ctx: commands.Context):
        if ctx.author.voice: update = {
            'Guild_ID': ctx.guild.id,
            'Voice_Channel_ID': ctx.author.voice.channel.id
        }
        else: update = {'Guild_ID': ctx.guild.id}
        bot_cfg.update(update)
    def call_async_method(self,method: callable, *args, **kwargs):
        self.loop.create_task(method(*args,**kwargs))
    async def join_voice(self) -> bool:
        cfg = bot_cfg.get()
        if 'Voice_Channel_ID' and 'Guild_ID' in cfg: vc = self.get_channel(cfg['Voice_Channel_ID'])
        else:
            print(f"No saved voice channel: please run command '{self.command_prefix}savelocation' while connected to a voice channel to save")
            return False
        if self.__voice_client == None: self.__voice_client = await vc.connect()
        else: await self.__voice_client.move_to(vc)
        return True
    async def play_audio(self, audio_source: discord.AudioSource):
        if self.__voice_client == None and not await self.join_voice(): return
        self.__voice_client.play(audio_source)
        self.__playing = True
    def stop_audio(self):
        if self.__voice_client != None and self.__voice_client.is_playing(): self.__voice_client.stop()
        self.__playing = False
    async def on_ready(self):
        self.ready.set()
    @property
    def playing(self):
        return self.__playing


def generate_bot() -> tuple[FadeBot, threading.Thread]:
    intents = discord.Intents.default()
    intents.message_content = True
    bot = FadeBot("X!", intents=intents)
    t = threading.Thread(target=bot.run,args=[fadebot_token])

    t.start()
    bot.ready.wait()
    return bot, t

    
    
    