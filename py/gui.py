import eel
from os.path import abspath

import eel.msIE
from gui_pages import pages

## Globals
current_page = ""
EMPTY_FUNCTION = lambda: None

eel.init('files')

global queue

def start_gui(track_queue, on_close, **kwargs):
    global queue
    queue = track_queue
    eel.start('../index.html', close_callback=on_close, **kwargs)
    print('DONE')
    
@eel.expose
def queue_song(location: str):
    queue.add_song_to_queue(location)
        

@eel.expose
def switch_page(pagename : str):
    '''Switches the content on the web gui to a differe page located at ../web/pages/<pagename>.html'''
    global current_page
    if pagename != current_page:
        eel.change_content(pages[pagename])
        eel.switch_active_nav(f'nav-{current_page}',f'nav-{pagename}')
        current_page = pagename

###########################
# DISCORD SETUP FUNCTIONS #
###########################

@eel.expose
def join_voice_channel(): pass
@eel.expose
def leave_voice_channel(): pass
@eel.expose
def change_discord_settings(settings): pass

#########################
# AUDIO PLAYER CONTROLS #
#########################
audio_player_controls = {
    '''A dictionary of callback functions that should be overwitten by the importer.'''
                                                        # Provided callback for each control should:
    "pause_toggle":                     EMPTY_FUNCTION, # toggle pause/resume audio 
    "skip_song":                        EMPTY_FUNCTION, # skip the current song
    "skip_song_fadeless":               EMPTY_FUNCTION, # skip the current song without crossfading
    "clear_queue":                      EMPTY_FUNCTION, # clear the queue
    "stop_playing":                     EMPTY_FUNCTION, # clear the queue and skip the current song without crossfade
    "queue_song":                       EMPTY_FUNCTION, # find a song at the URL and add it to the queue
    "insert_song":                      EMPTY_FUNCTION, # find the song and add it at the beginning of the queue
    "replace_queue_with_song":          EMPTY_FUNCTION, # find the song, then clear the queue and add the song to the (now empty) queue
    "replace_all_with_song":            EMPTY_FUNCTION, # find the song the URL, then clear the queue and add the song to the queue, then skip the current song
    "queue_playlist":                   EMPTY_FUNCTION, # find a user playlist with the specified id and add it to the queue
    "insert_playlist":                  EMPTY_FUNCTION, # find a playlist and add it
    "replace_queue_with_playlist":      EMPTY_FUNCTION,
    "replace_all_with_playlist":        EMPTY_FUNCTION
}
@eel.expose
def send_audio_player_control_message(message_type,*args):
    audio_player_controls[message_type](*args)



@eel.expose
def get_playlists(): pass
@eel.expose
def get_queue(): pass
@eel.expose
def get_song_timer(): pass
