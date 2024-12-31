import bot, gui, AudioHandler, threading, os
from time import sleep

# A bunch of code goes here
# ..., functions that will
# ... connect all the aspects
# ... of this project.

# Right now, it just runs the GUI

def gui_func():
    gui.start_gui(mode='chrome',size=(960,540))

def bot_func():
    pass

def ain_func():
    queue = AudioHandler.TrackQueue(1.,2,[2.,2.])
    queue.add_playlist_to_queue([],[{'location':"https://www.youtube.com/watch?v=OzyC4RVTilI"}],[])
    queue.add_song_to_queue("https://www.youtube.com/watch?v=nsjgcZUZ-b0")
    sleep(5)
    print(queue.start,queue.start._nxt,queue.start._nxt._nxt,queue.start._nxt._nxt._nxt)
    cmd = 'skip_playlist'
    for i in range(2000):
        d = queue.read()
        if i == 999:
            print(cmd)
            queue.command(cmd)
        if i%50 == 49:
            print(d[:10])
        sleep(0.01)
    
    print('?')
    print(queue.history)
    queue.close()
    print(".")

if __name__ == '__main__':
    #gui_thread = threading.Thread(target=gui_func)
    #ain_thread = threading.Thread(target=ain_func)
    
    ain_func()

    #gui_thread.start()
    #ain_thread.start()

    #gui_thread.join()
    #ain_thread.join()

    
    