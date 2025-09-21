from AudioHandler import TrackQueue, DigitalAudioTransformer, REPEAT
import threading, sys
from cfg import aio_cfg
queue = TrackQueue(**(aio_cfg.get()))
from time import sleep

from bot import generate_bot
import gui

def gui_func(callback, bot):
    thread = threading.Thread(target=gui.start_gui,args=[queue,bot,callback])
    thread.start()
    return thread

def bot_func():
    bot, thread = generate_bot()

    bot.call_async_method(bot.play_audio,queue)

    return bot, thread

if __name__ == '__main__':
    threading
    bot, bot_thread = bot_func()
    def close(*a):
        queue.close()
        bot.stop_audio()
        bot.call_async_method(bot.close)
        raise SystemExit
    
    gui_thread = gui_func(close, bot)
    
    gui_thread.join()
    bot_thread.join()
    