import gui, threading, os
from bot import generate_bot
from time import sleep
from cfg import aio_cfg
from AudioHandler import TrackQueue, DigitalAudioTransformer, REPEAT


# A bunch of code goes here
# ..., functions that will
# ... connect all the aspects
# ... of this project.

# Right now, it just runs the GUI

def gui_func():
    gui.start_gui(mode='firefox-app',size=(960,540))

def bot_func():
    bot, thread = generate_bot()
    queue = TrackQueue(1.,REPEAT.PLM,[5.,5.])

    bot.call_async_method(bot.play_audio,queue)
    
    queue.add_playlist_to_queue([],[{'location':"https://www.youtube.com/watch?v=fcVdS60wyOQ",'start':30.0},{'location':'https://www.youtube.com/watch?v=GQPZivMuQvk'}],[])
    queue.add_song_to_queue("https://www.youtube.com/watch?v=4cROKrDAguo",volume=0.5)
    queue.add_song_to_queue("https://www.youtube.com/watch?v=N0KlwU8O5bA")
    queue.add_song_to_queue("https://www.youtube.com/watch?v=55IyfpL58gw")

    thread.join()

if __name__ == '__main__':
    gui_thread = threading.Thread(target=gui_func)
    #ain_thread = threading.Thread(target=ain_func)
    
    #bot_func()
    #ain_func()

    gui_thread.start()
    #ain_thread.start()

    gui_thread.join()
    #ain_thread.join()

    
    