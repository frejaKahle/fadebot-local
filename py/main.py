import bot, gui, AudioHandler

# A bunch of code goes here
# ..., functions that will
# ... connect all the aspects
# ... of this project.

# Right now, it just runs the GUI

if __name__ == '__main__':
    gui.switch_page = lambda x: print(f"Switching to f{x}")
    gui.start_gui(mode='chrome',size=(960,540))