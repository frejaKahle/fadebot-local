import eel
from os.path import abspath

import eel.msIE
from gui_pages import pages
import cfg

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
def get_playlists(): pass
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


