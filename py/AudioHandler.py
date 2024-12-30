import math, threading, asyncio, yt_dlp
import numpy as np
from io import BufferedIOBase
from discord import FFmpegPCMAudio
from mutagen import mp3, wave, aiff, aac, ogg, File
from types import SimpleNamespace
from typing import IO, Callable, Generator, Any, Self
from time import time, sleep
from queue import Queue
from collections import deque


FRAMESIZE = 3840                                # Length of an audio frame in bytes
FRAMESIZE_I = FRAMESIZE//2                      # length of an audio frame in integers
ZERO_FRAME = bytes(FRAMESIZE)                   # A placeholder audio frame of silence
FRAMELENMS: int = 20                            # Length of an audio frame in ms
FRAMELENSEC: float = FRAMELENMS/1000            # Length of an audio frame in s
FPS: int = 1000/FRAMELENMS                      # Audio frames per second

MAXCROSSFADE_S = 12                                         # Max setting for crossfade
MAXCROSSFADE_MS: int = MAXCROSSFADE_S * 1000                # ^ in miliseconds
MAXCROSSFADE_FRAMES: int = MAXCROSSFADE_MS // FRAMELENMS    # ^ in audio frames
MAXCROSSFADE_BYTES: int = MAXCROSSFADE_FRAMES * FRAMESIZE   # ^ in bytes

REPEAT = SimpleNamespace()
REPEAT.OFF = 0  # Repeat setting for no repeat
REPEAT.ONE = 1  # Repeat setting for repeating one song
REPEAT.PLM = 2  # Repeat setting for repeating the 'main' section of a playlist until skipped (plays 'outro' when skipped)
REPEAT.PLA = 3  # Repeat setting for repeating one playlist until skipped (does not play 'outro' when skipped)
REPEAT.ALL = 4  # Repeat setting for repeating everything in the queue

OPTS = SimpleNamespace()
OPTS.FFMPEG = lambda: {'before_options':'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
                       'options':'-vn'}
OPTS.YTDLP = {'format':'bestaudio'}

def round_to_frame(n):
    '''Takes a number of miliseconds and rounds it to the nearest audio frame timing in ms'''
    return round(n*FRAMELENSEC,0) * FPS

# An array that holds np arrays of integers
#  designed to be shifted many times in a fixed space
# It does this by cycling integers representing
#  position and end of array 
class CircularAudioBuffer:
    def __init__(self, array: list[bytes] = [b''], array_len: int = MAXCROSSFADE_FRAMES):
        if array_len < len(array):
            raise IndexError("Array length too small to fit supplied data.")
        self.array : np.ndarray[Any, np.ndarray[Any, np.int16]] = np.array([np.frombuffer(elem,'int16',count=1920) for elem in array])
        self.array.reshape(array_len)
        self.length = array_len
        self.pos = 0
        self.end = 0
        self.lock = threading.Lock()
        self.lock_writes = threading.Condition(threading.Lock())
        self.wait_for_read = threading.Condition(threading.Lock())
        self.wait_for_write = threading.Condition()

    @property
    def size(self) -> int:
        with self.lock:
            return self.end - self.pos if self.end >= self.pos else self.end + self.length - self.pos
    def __iter__(self):
        return self
    def __next__(self):
        self.wait_for_write.wait_for(           # Ensure buffer isn't empty
            lambda: self.size > 0)              # and acquire buffer lock
        self.lock.acquire(timeout=-1)

        self.pos = (self.pos + 1) % self.length # Increment read head
        d = self.array[self.pos]                # get data from the 
        
        self.lock.release()                     # release buffer lock
        self.wait_for_read.notify()             # and notify write thread

        if d.size == 0:                         # Output or stop iteration
            raise StopIteration                 #
        return d                                #
    
    def __len__(self): 
        with self.lock: return self.length

    def __getitem__(self,key) -> np.ndarray[Any, np.int16]:
        with self.lock:
            return self.array[(key + self.pos) % self.length]
    def __setitem__(self,key,value: bytes | np.ndarray[Any, np.int16]):
        if isinstance(value,bytes):
            value = np.frombuffer(value,'int16',count=1920)
        with self.lock:
            self.array[(key + self.pos) % self.length] = value
    def write(self, data: bytes | np.ndarray[Any, np.int16]):
        '''Writes audio to the buffer supplied as a bytes object or np array of ints'''
        if isinstance(data,bytes):
            data = np.frombuffer(data,'int16',count=1920)

        self.wait_for_read.wait_for(           # Ensure buffer isn't full
            lambda: self.size < self.length-1)  # 
        self.lock.acquire(-1)                   # acquire buffer lock
        self.lock_writes.acquire(-1)            # and writing lock

        self.array[self.end] = data             # write the data
        self.end = (self.end + 1) % self.length # increment write head

        self.lock.release()                     # Release buffer lock,
        self.lock_writes.release()              # Release write lock
        self.wait_for_write.notify()            # Notify read thread
    
    def resize(self, size: int):
        '''resizes the audio buffer'''
        self.lock_writes.acquire(-1)            # acquire write lock
        self.wait_for_read.wait_for(            # wait for the buffer
            lambda: self.size <= size)          #  to be empty enough
        self.lock.acquire(-1)                   # acquire buffer lock

        self.array = np.array(                  # copy array to a new
            [a for a in iter(self)])            #  numpy array
        self.array = np.resize(self.array,size) # resize the array to correct size
        self.pos = 0                            # reset read head
        self.end = self.length-1                # set write head to the end of data
        self.length = size                      # set length to the new size

class SingleBufferedAudio:
    def __init__(self):
        self.audio: np.ndarray[Any, np.int16] | None = None
        self.w = threading.Event()
        self.r = threading.Event()
        self.w.set()
    
    def __iter__(self): return self

    def write(self, data: bytes | np.ndarray[Any, np.int16]):
        '''Writes audio to the buffer supplied as a bytes object or np array of ints'''
        if isinstance(data,bytes):
            data = np.frombuffer(data,'int16',count=1920)
        self.w.wait()
        self.audio = data
        self.w.clear()
        self.r.set()

    def read(self) -> np.ndarray[Any, np.int16]:
        '''Reads audio from the buffer'''
        self.r.wait()
        data = self.audio
        self.r.clear()
        self.w.set()
        return data
    def __next__(self) -> np.ndarray[Any, np.int16]:
        d = self.read()
        if d.size == 0:
            raise StopIteration
        return d

class ProgessibleFFmpegPCMAudio(FFmpegPCMAudio):
    def __init__(self, source: str | BufferedIOBase, end_time: int, pass_time: int = 0, *, executable: str = 'ffmpeg', pipe: bool = False,  stderr: IO[bytes] | None = None, before_options: str | None = None, options: str | None = None) -> None:
        ''' This class is a subclass of PCMAudio that keeps track of progress through the audio source
        :int pass_time: What time in the source the audio should jump to at the start
        :int end_time: What time in the source the audio should stop at, if not the end (-1 for infinity)'''
        super().__init__(source, executable=executable, pipe=pipe, stderr=stderr, before_options=before_options, options=options)
        self.raw_queue: SingleBufferedAudio | CircularAudioBuffer = SingleBufferedAudio()
        self.source_progress = 0        # progress through the source in ms
        self.true_progress = 0          # play progress in ms
        self.end_time = end_time        # end time in ms
        self.pass_time = pass_time      # starting offset in ms
        self.create_writer()
    class LargeBuffered(): 
        def __init__(self): 
            self.raw_queue = CircularAudioBuffer()

    def create_writer(self):
        '''creates an async task to buffer audio from the source'''
        l = asyncio.get_event_loop()
        l.create_task(self.write())
    async def write(self):
        '''coroutine for writing audio from the source to the buffer'''
        while(self.end_time > 0 and self.source_progress + self.pass_time >= self.end_time):
            data = super().read()
            self.source_progress += 20
            self.raw_queue.write(data)

        super().cleanup()   # ends the audio early if the end time is reached
        self.raw_queue.write(np.array([]))        
    
    def read(self) -> np.ndarray[Any, np.int16] | None:
        '''Reads audio from the PCMAudio source'''
        self.true_progress += 20
        return next(self.raw_queue)
    
    def check_time(self) -> float:
        '''Returns the progress through the audio source as a float (0-1)'''
        return (self.true_progress + self.pass_time) / 1000
    def end_in(self, seconds: float):
        new_time = self.pass_time + self.progress + int(seconds * 1000)
        if self.end_time < 0:
            self.end_time = new_time
        else:
            self.end_time = min(self.end_time,new_time)
    @property
    def time_to_end(self) -> int:
        return self.end_time - self.pass_time - self.true_progress
        
class Track():
    def truefade(fade_progress_after_frame: int, fade_time: int):
        fade_progress_before_frame = min(max((fade_progress_after_frame - FRAMELENMS)/fade_time,0),1)
        fade_progress_after_frame = min(max(fade_progress_after_frame/fade_time,0),1)
        m = np.linspace(fade_progress_before_frame,fade_progress_after_frame,FRAMESIZE_I,False)
        return m
    def fastfade(fade_progress_after_frame: int, fade_time: int):
        m = min(max(fade_progress_after_frame/fade_time,0),1)
        return m
        
    def __init__(self,
                 stream_creator: Callable[[],ProgessibleFFmpegPCMAudio], name: str, artist:  str, image: str | None,
                 album: str | None, year: int, volume: float = 1.0, fade_settings: Callable[[],tuple[int,int]] = lambda: (0, 0),
                 fade_function: Callable[[np.ndarray[Any,np.int16],float,float],np.ndarray[Any,np.int16]] = fastfade) -> None:
        '''
        This class represents an audio source that also includes settings such as volume and crossfade timings. The stream is created by a callback funtion to allow restarting the song.
        stream_creator -- A function that returns a new copy of the audio stream in case the track needs to be restarted
        name -- Title of the track
        artist -- The name of the artist that made the track (or uploader in case of a standard youtube video)
        image -- A path string that links to the prefered art for the song, or None in case no image is available
        album -- The name of the album the track is on, or None if it is not from an album
        year -- Year the track was released/uploaded
        volume -- track specific volume (can be set manually or in a track's settings in a playlist)
        fade_settings -- A function that returns the length of fade ins and fade outs in ms.
        fade_function -- A function that determines how the data gets faded in and out computationaly. truefade is slower, but slightly more accurate than fastfade
        '''
        self.stream_creator: Callable[[],ProgessibleFFmpegPCMAudio] = stream_creator
        self.name: str = name
        self.artist: str = artist
        self.image: str | None = image
        self.album: str | None = album
        self.year: str | None = year

        self.volume = min(max(volume,1.0),0.001)                # Volume 
        self.fade_settings: Callable[[],tuple[int,int]] = fade_settings  # Fade in/out timing in ms
        self.fade_progress: int = 0
        self.fade_function: Callable[[np.ndarray[Any,np.int16],float,float]
                                     ,np.ndarray[Any,np.int16]] = fade_function # Fade multiplier fuction

        self.stream: ProgessibleFFmpegPCMAudio
        self.start()
    class Fade_In():
        '''A song that is currently fading in (for internal use)'''
        def read(self):
            self.fade_progress += 20
            data = self.stream.read()
            m = self.fade_function(self.fade_progress / self.fade_settings()[0], self.fade_settings()[0])
            if self.fade_progress_p >= 1:
                self.__class__ = Track
            return data, m * self.volume
    class Fade_Out():
        '''A song that is currently fading out (for internal use)'''
        def read(self):
            data = self.stream.read()
            m = self.fade_function(self.stream.end_time - self.stream.true_progress, self.fade_settings()[1])
            return data, m * self.volume
    def start(self): 
        self.stream = self.stream_creator()
        if self.fade_settings()[0] > 0:
            self.__class__ = self.Fade_In
    def restart(self): self.start()
    def read(self):
        data = self.stream.read()
        if self.stream.true_progress + self.fade_settings()[1] >= self.stream.end_time or data.size == 0:
            self.__class__ = self.Fade_Out
        return data, self.volume
    @property
    def percent_progress(self) -> float:
        '''Returns a value between 0 and 1 representing the song's completion'''
        return self.stream.check_time / self.duration
    @property
    def progress_seconds(self) -> int:
        '''Returns the current temporal position of the song progress in seconds from 0'''
        return self.stream.check_time()
    @property
    def section_seconds(self) -> int:
        '''Returns the current temporal position of the song progress in seconds from start position'''
        return self.stream.check_time()

    def _verify_and_apply_section(stream_url: str, limits: tuple[float, float], duration, min_dur: int, **song_info) -> Self:
        '''Generates a song object from a stream, start/end limits, duration of the audio, minimum duration (fade times added), and song info.'''
        if max(min_dur,1) > duration: raise ValueError(f'Audio source must be at least {max(min_dur,1)} seconds in length.')
        end: float = round_to_frame(1000*(duration if limits[1] < 0 else max(min(limits[1],duration),1)))
        start: float = round_to_frame(1000*(max(min(math.ceil(limits[0] / FRAMELENSEC),0), end-1)))
        ffopts = OPTS.FFMPEG()
        ffopts['before_options'] = f'-ss {start}ms ' + ffopts
        sc = lambda: ProgessibleFFmpegPCMAudio(stream_url, **ffopts, pass_time=start, end_time=end)
        return Track(sc, **song_info)

    @classmethod
    def from_yt(cls, url: str, limits: tuple[float, float] = (0.0,-1.0), min_dur: int = 5, volume: float = 1.0, fade_settings: tuple[float, float] = (-1.0,-1.0)) -> Self:
        with yt_dlp.YoutubeDL(OPTS.YTDLP) as ydl:
            song_info = ydl.extract_info(url, download=False)
            durtn = song_info["duration"]
            surl = song_info["url"]
            try:
                name = song_info['track']
                artist = song_info['artist']
                album = song_info['album']
                year = song_info['release_year']
            except:
                name = song_info['title']
                artist = song_info['channel']
                album = None
                year = int(song_info['release_date'][:4])
            return cls._verify_and_apply_section(surl, limits, durtn, min_dur, 
                                            name = name, artist = artist,
                                            album = album, year = year,
                                            image = song_info['thumbnail'],
                                            volume = volume, fade_settings = fade_settings)
    @classmethod
    def from_file(cls,file_location: str, limits: tuple[float, float] = (0.0,-1.0), min_dur: int = 5, volume: float = 1.0, fade_settings: tuple[float, float] = (-1.0,-1.0)) -> Self:
        match file_location:
            case x if len(x) < 5: raise ValueError("Filename invalid: Too Short")
            case x if x[-4:] == '.mp3':     fi = mp3.MP3(x)
            case x if x[-4:] == '.wav':     fi = wave.WAVE(x)
            case x if x[-5:] == '.aiff':    fi = aiff.AIFF(x)
            case x if x[-4:] == '.aac':     fi = aac.AAC(x)
            case x if x[-4:] == '.ogg':     fi = ogg.OggFileType(x)
            case _: raise ValueError("Filetype invalid: Must be: .mp3, .wav, .aiff, .aac, or .ogg")
        durtn = fi.info.length
    
        return cls._verify_and_apply_section(file_location, limits, durtn,
                                name = fi['TIT2'][0], artist = fi['TPE1'][0],
                                album = fi['TALB'][0], year = int(fi['TDRC'][0]),
                                image = None,
                                volume = volume, fade_settings = fade_settings)


class QueueNode:
    def __init__(self, prevnode: Self | None = None, nextnode: Self | None = None):
        self._prv: Self | None = prevnode
        self._nxt: Self | None = nextnode
        self._arrived: Self | None = None
        self.lock = threading.Lock()
    def insert(self, node: Self | Track):
        self.lock.acquire()
        prv = self._prv
        if isinstance(node, Track):
            node = TrackNode(node, prv, self)
        else:
            node.lock.acquire()
            node._prv = prv
            node.lock.release()
        if prv:
            prv.lock.acquire()
            prv._nxt = node
            prv.lock.release()
        self._prv = node
        self.lock.release()
        node._nxt = self
    def append(self, node: Self | Track):
        self.lock.acquire()
        nxt = self._nxt
        if isinstance(node, Track):
            node = TrackNode(node, self, nxt)
        else:
            node.lock.acquire()
            node._nxt = nxt
            node.lock.release()
        if nxt:
            nxt.lock.release()
            nxt._prv = node
            nxt.lock.release()
        self._nxt = node
        self.lock.release()

    def getnext(self, repeat_setting: int = 0) -> Self | None:
        self.lock.acquire()
        n = self._nxt
        self.lock.release()
        if n.__class__ == PlaylistDelimiter:
            return n.getnext(repeat_setting)
        return n
    def getbeginning(self):
        with self.lock: p = self._prv
        if p == None: return self
        return p.getbeginning()
    def __contains__(self, item, s = True):
        with self.lock:
            n = self.getbeginning() if s else self._nxt
        return n.__contains__(item, s = False) if n else False
class TrackNode(QueueNode):
    def __init__(self, track: Track, prevnode: Self | None = None, nextnode: Self | None = None):
        super().__init__(prevnode,nextnode)
        self.track = track
class PlaylistDelimiter(QueueNode):
    def __init__(self,return_to_node_with_setting: tuple[int,TrackNode], max_repeats: int = -1, repeat_regardles:bool = False, prevnode: Self | None = None, nextnode: Self | None = None):
        super().__init__(prevnode,nextnode)
        self.repeat_setting: int = return_to_node_with_setting[0]   # 2 for main section and 3 for outro section
        self.return_node = return_to_node_with_setting[1]           # node to return to with specific repeat settings
        self.count: int = max_repeats+1                             # a count of how many times this delimiter can be passed
        self.regard: bool = repeat_regardles                        # should the playlist delimiter repeat without concern for the repeat setting
    def getnext(self, repeat_setting: int = 0) -> QueueNode | None:
        with self.lock:
            self.count -= 1
            if (repeat_setting == self.repeat_setting or self.regard) and self.count != 0:
                return self.return_node
        return super().getnext(repeat_setting)

class TrackQueue(FFmpegPCMAudio):
    def __init__(self, volume: float = 1.0, repeat: int = REPEAT.OFF,
                 default_fade: tuple[float,float] = 0.0) -> None:
        self.volume = volume
        self.repeat = repeat
        self.fade = default_fade
        
        self.writer = threading.Thread(target=self.writer_thread,name="Fadebot Queue Audio Bufferer")
        # Resources that belong to the writer thread:
        self.current: deque[TrackNode] = []
        self.history: deque[TrackNode] = []

        #shared resources
        self.start: TrackNode | None = None
        self.end: QueueNode | None = None
        self.stop = False
        self.buffer = SingleBufferedAudio()

        # finish setting up
        self.writer.start()
    
    def read(self):
        return self.buffer.read().tobytes()
    async def write(self):
        async def add_from_tracks(data: np.ndarray[Any,np.int16]):
            for i in range(len(self.current)):
                inp = self.current[i].track.read()
                data += inp[0] * (inp[1] * self.volume)
                return data
        while(not self.stop):
            data = np.zeros(1920,np.int16)
            f = add_from_tracks(data)
            try: data = await asyncio.wait_for(f, timeout=FRAMELENSEC*.9)
            except asyncio.TimeoutError: pass    

    def writer_thread(self):
        async def get_new_tracks():
            async def add_new_track(node):
                if node in self.current:
                    self.current.append(self.current.pop(self.current.index(t)))
                else: 
                    self.current.append(node)
                node.track.start()
                asyncio.sleep(node.track.fade_settings[0]/1000.)
            def add_track_history(node):
                if node in self.current:
                    i = len(self.current) - self.current.index(node)
                    self.current.rotate(i)
                else: self.current.append(node)
            while(not self.stop):
                if self.current:                                            # IF THERE ARE ONE OR MORE CURRENTLY PLAYING SONGS:
                    if (nxt := (now_playing := self.current[-1]).getnext()):# -> IF the most recent track has a track following it in the queue:
                        tte: int = now_playing.stream.time_to_end           # -> -> find the playing track's time till end
                        with nxt.lock:                                      # -> -> lock the following track
                            b = nxt.track.fade_settings[0] >= tte           # -> -> IF the following track can start fading in:
                        if b: 
                            await add_new_track(nxt)                        # -> -> -> add it to the queue
                            continue
                    if self.current[0].track.percent_progress >= 1.:        # -> IF the oldest playing track is out of audio:
                        t = self.current.popleft()                          # -> -> remove it from the currently playong songs
                        add_track_history(t)                                # -> -> and add it to the history
                    await asyncio.sleep(FRAMELENSEC)                        # -> Wait one audio frame before looping
                else:                                                       # IF THERE ARE NO CURRENTLY PLAYING SONGS:
                    if self.history:                                        # -> IF there is a history of tracks
                        t = self.history[-1].getnext()                      # -> -> IF the latest addition to the history has a new following track in the queue
                        if t: await add_new_track(t)                        # -> -> -> add that following track to the currently playing list
                    elif self.start: await add_new_track(self.start)        # -> IF the queue is new and a song has been added: add it to the currently playing songs
                    else: await asyncio.sleep(0.2)                          # -> Wait a fifth of a second

                

        t1 = asyncio.get_event_loop().create_task(self.write(self))


    @property
    def now_playing(self):
        return self.current[-1]



        
        

            
    





"""
class FadeAudioBuffer(CircularAudioBuffer):
    def __init__(self, extra_audio_frames: int = 0, fade_in_time: Callable[[],float] = lambda: 0.0, fade_out_time: Callable[[],float] = lambda: 0.0) -> None:
        super().__init__(extra_audio_frames)
        self.fade_in: Callable[[],int] = int(fade_in_time() / FRAMELENSEC)
        self.fade_out: Callable[[],int] = int(fade_out_time() / FRAMELENSEC)
    
    @property
    def target_size(self):
        return self.fade_out() + 1


class FadeAudioWriter():
    def __init__(self, source: Callable[[],tuple[ProgessibleFFmpegPCMAudio | None,tuple[float,float]]], output_buffer: BufferedIOBase, fade_time : Callable[[],float] = lambda: 0.0) -> None:
        '''
        :Callable source: a function provided to a FadeAudioWriter instance that allows for changes in the stream. For normal use create a SongQueue object and pass its getstream function as this parameter.
        :float fade_time: How many seconds of crossfade to have.'''
        self.inputs: list[Song] = []
        self.queue = Queue()
        if not output_buffer.writable(): raise TypeError("Audio writer's output buffer must be a writeable buffer.")
        self.output: BufferedIOBase = output_buffer                     # list of output buffers for multiple audio outputs

    async def get_next_frame(self):
        if not self.inputs: return ZERO_FRAME

        
        for inp in self.inputs:
            np.frombuffer
"""