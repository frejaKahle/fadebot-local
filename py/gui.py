import eel
from os.path import abspath

import eel.msIE
from gui_pages import pages
import cfg

## Globals
current_page = ""
EMPTY_FUNCTION = lambda: None

eel.init('files')

global queue, bot

def start_gui(track_queue, discord_bot, on_close, **kwargs):
    global queue, bot
    queue = track_queue
    bot = discord_bot
    eel.start('../index.html', close_callback=on_close, **kwargs)
    print('DONE')

@eel.expose
def switch_page(pagename : str):
    '''Switches the content on the web gui to a differe page located at ../web/pages/<pagename>.html'''
    global current_page
    if pagename != current_page:
        eel.change_content(pages[pagename])
        eel.switch_active_nav(f'nav-{current_page}',f'nav-{pagename}')
        current_page = pagename

############################
# QUEUE RELATED FUNCTIUONS #
############################

@eel.expose
def queue_song(location: str):
    queue.add_song_to_queue(location)

@eel.expose
def command(command: str):
    queue.command(command)


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
def get_queue(): pass
@eel.expose
def get_song_timer(): pass
