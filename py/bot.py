import discord
from discord.ext import commands, tasks
from private.cfg import fadebot_app_id, fadebot_token
from cfg import def_cfg, usr_cfg

def generate_bot():
    intents = discord.Intents().all()
    client = discord.Client(intents=intents)
    bot = commands.Bot(command_prefix="X!", intents=intents)

    @bot.command(name = 'savelocation', help ='Saves the voice channel you are in to the config file')
    @commands.has_permissions(administrator = True)
    async def save_location(ctx: commands.Context):
        if ctx.author.voice: update = {
            'Guild_ID': ctx.guild.id,
            'Voice_Channel_ID': ctx.author.voice.channel.id
        }
        else: update = {'Guild_ID': ctx.guild.id}
    usr_cfg.call(usr_cfg)