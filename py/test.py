import discord, yt_dlp
#,'hls_prefer_native':{'m3u8': 'ffmpeg'}
with yt_dlp.YoutubeDL({'format':'bestaudio','extractor_args':{'youtube':{'player_client':['-mweb','ios'],'skip':['dash'],'player_skip':['webpage','configs','js']}}}) as ydl:
    song_info = ydl.extract_info("https://www.youtube.com/watch?v=OzyC4RVTilI", download=False)

a = discord.FFmpegPCMAudio(song_info['url'], before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',options='-vn',)
for i in range(20):
    print(a.read())

