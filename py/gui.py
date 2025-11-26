import eel
from os.path import abspath, isfile, join
import json
import time

import eel.msIE
from gui_pages import pages
import cfg
from AudioHandler import Track
## Globals
EMPTY_FUNCTION = lambda: None

eel.init('files')

global queue, bot, g



def start_gui(track_queue, discord_bot, on_close, **kwargs):
    global queue, bot, g
    queue = track_queue
    bot = discord_bot
    g = eel.spawn(update_np)
    eel.start('../index.html', close_callback=on_close, block=True, **kwargs)

@eel.expose
def get_page(pagename : str):
    '''Switches the content on the web gui to a differe page located at ../web/pages/<pagename>.html'''
    return pages[pagename]

############################
# QUEUE RELATED FUNCTIUONS #
############################

@eel.expose
def queue_song(location: str):
    queue.add_song_to_queue(location)

@eel.expose
def queue_preloaded_song(info: dict):
    idx1 = info['stream_url'].find("?expire=")
    idx2 = info['stream_url'].find("&")
    if(idx1 != -1 and idx2 != -1):
        i = float(info['stream_url'][idx1 + 8:idx2])
        if (time.time() > i):
            info.update(Track.get_playlist_info(info['original_url'])[0])
    queue.add_song_to_queue( location = "",pre_searched = True, **info)
    return info

@eel.expose
def queue_playlist(info: dict[list[dict]]):
    intro = info['i']
    main  = info['m']
    outro = info['o']
    queue.add_playlist_to_queue(intro, main, outro)

@eel.expose
def command(command: str):
    queue.command(command)

@eel.expose
def queue_info():
    return queue.as_dictionary()

#####################
# DISCORD FUNCTIONS #
#####################

@eel.expose
def start_audio():
    if not bot.playing:
        bot.call_async_method(bot.play_audio,queue)

@eel.expose
def change_discord_settings(settings):
    cfg.bot_cfg.set(settings)

@eel.expose
def get_playlists() -> dict:
    with open('config\\playlists.json', 'r') as jsonfile:
        try:
            playlists: dict = json.load(jsonfile)
        except:
            playlists: dict = {} 
    return playlists
@eel.expose
def get_queue():
    return queue.current_queue
@eel.expose
def get_song_timer(): pass
@eel.expose
def get_playing():
    return queue.currently_playing

@eel.expose
def debug(): queue.debug()
@eel.expose
def aio_config(set_to = None):
    if set_to == None:
        return cfg.aio_cfg.get()
    else:
        cfg.aio_cfg.update(set_to)
@eel.expose
def bot_config(set_to = None):
    if set_to == None:
        return cfg.bot_cfg.get()
    else:
        cfg.bot_cfg.update(set_to)

def update_np():
    print("running")
    while (not queue.stop.is_set()):
        songs = queue.update_playing.green_get()
        print(songs)
        eel.nowPlaying(songs)()
    print("stopping")
    g.kill()

######################
# PLAYLIST FUNCTIONS #
######################

@eel.expose
def get_playlist_from_url(name: str, url: str) -> bool:
    try:
        with open('config\\playlists.json', 'r') as jsonfile:
            try:
                playlists: dict = json.load(jsonfile)
            except:
                playlists: dict = {}
    except:
        playlists: dict = {}
    if name in playlists.keys(): return False
    playlist_info = Track.get_playlist_info(url)
    if not playlist_info: return False
    playlists.update({name:{'image': playlist_info[0]['image'] if playlist_info else "",'i':[],'m':playlist_info,'o':[]}})
    with open('config\\playlists.json', 'w+') as jsonfile:
        json.dump(playlists, jsonfile, ensure_ascii=False, indent=4)
        return True
@eel.expose
def get_track_from_url(url: str) -> list[dict]:
    if url:
        return Track.get_playlist_info(url)
    return None
@eel.expose
def save_track(playlist_key: str, section_key: str, index: int, track: dict):
    with open('config\\playlists.json', 'r') as jsonfile:
        try:
            playlists: dict = json.load(jsonfile)
        except:
            playlists: dict = {}
    if playlist_key not in playlists.keys(): return False
    playlist = playlists[playlist_key][section_key]
    if index < len(playlist):
        playlist[index] = track
    else:
        playlist.append(track)
    with open('config\\playlists.json', 'w+') as jsonfile:
        json.dump(playlists, jsonfile, ensure_ascii=False, indent=4)
        return True