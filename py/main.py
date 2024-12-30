import bot, gui, AudioHandler, threading, os

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
    pass

if __name__ == '__main__':
    gui_thread = threading.Thread(target=gui_func)
    
    gui_thread.start()

    gui_thread.join()

    
    