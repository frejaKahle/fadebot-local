import math, threading, asyncio, yt_dlp
import numpy as np
from io import BufferedIOBase
from discord import FFmpegPCMAudio
from mutagen import mp3, wave, aiff, aac, ogg, File
from types import SimpleNamespace
from typing import IO, Callable, Any, Self, Optional
from time import time, sleep
from queue import Queue
from collections import deque


FRAMESIZE = 3840                                # Length of an audio frame in bytes
FRAMESIZE_I = FRAMESIZE//2                      # length of an audio frame in integers
ZERO_FRAME = np.zeros(FRAMESIZE_I,np.int16)     # A placeholder audio frame of silence
ZERO_FRAME_FLOAT = ZERO_FRAME.astype(np.float64)# A placeholder audio frame of silence (float)
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
OPTS.FFMPEG = {'before_options':'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
                       'options':'-vn'}
OPTS.YTDLP = {'format':'bestaudio','noplaylist':True}

def round_to_frame(n):
    '''Takes a number of miliseconds and rounds it to the nearest audio frame timing in ms'''
    return round(n*FRAMELENSEC,0) * FPS

class SingleBufferedAudio:
    def __init__(self):
        self.audio: np.ndarray = ZERO_FRAME.copy()
        self.w = threading.Event()
        self.r = threading.Event()
        self.w.set()

    def write(self, data: bytes | np.ndarray):
        '''Writes audio to the buffer supplied as a bytes object or np array of ints'''
        if isinstance(data,bytes):
            data = np.frombuffer(data,'int16')
        self.w.wait()
        self.audio = data
        self.w.clear()
        self.r.set()

    def read(self) -> np.ndarray:
        '''Reads audio from the buffer'''
        self.r.wait()
        data = self.audio
        self.r.clear()
        self.w.set()
        return data

class ProgressibleFFmpegPCMAudio(FFmpegPCMAudio):
    def __init__(self, source: str | BufferedIOBase, end_time: int, pass_time: int = 0, **kwargs) -> None:
        ''' This class is a subclass of PCMAudio that keeps track of progress through the audio source
        :int pass_time: What time in the source the audio should jump to at the start
        :int end_time: What time in the source the audio should stop at, if not the end (-1 for infinity)'''
        super().__init__(source, **kwargs)
        self.raw_queue = SingleBufferedAudio()
        self.source_progress = 0        # progress through the source in ms
        self.true_progress = 0          # play progress in ms
        self.end_time = end_time        # end time in ms
        self.pass_time = pass_time      # starting offset in ms
        self.thread: threading.Thread
        
    def create_writer(self):
        '''creates an async task to buffer audio from the source'''
        self.thread = threading.Thread(target=self.write)
        self.thread.start()
    def write(self):
        '''coroutine for writing audio from the source to the buffer'''
        while(self.end_time > 0 and self.source_progress + self.pass_time <= self.end_time):
            data = super().read()
            self.source_progress += 20
            self.raw_queue.write(data)

        self.raw_queue.write(ZERO_FRAME.copy())
        self.raw_queue.write(np.array([]))        
    def end(self):
        self.end_time = 1
        self.read()
        self.thread.join()
    def read(self) -> np.ndarray[Any, np.int16] | None:
        '''Reads audio from the PCMAudio source'''
        self.true_progress += 20
        return self.raw_queue.read()
    
    def check_time(self) -> float:
        '''Returns the progress through the audio source as a float (0-1)'''
        return (self.true_progress + self.pass_time) / 1000
    def end_in(self, miliseconds: int):
        new_time = self.pass_time + self.source_progress + miliseconds - FRAMELENMS
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
                 stream_creator: Callable[[],ProgressibleFFmpegPCMAudio], name: str, artist:  str, image: str | None,
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
        self.stream_creator: Callable[[],ProgressibleFFmpegPCMAudio] = stream_creator
        self.name: str = name
        self.artist: str = artist
        self.image: str | None = image
        self.album: str | None = album
        self.year: str | None = year

        self.volume = max(min(volume,1.0),0.001)                # Volume 
        self.fade_settings: Callable[[],tuple[int,int]] = fade_settings  # Fade in/out timing in ms
        self.fade_progress: int = 0
        self.fade_function: Callable[[np.ndarray[Any,np.int16],float,float]
                                     ,np.ndarray[Any,np.int16]] = fade_function # Fade multiplier fuctio
        self.stream: ProgressibleFFmpegPCMAudio | None = None

    def start(self): 
        self.stream = self.stream_creator()
        self.stream.create_writer()
        if self.fade_settings()[0] > 0:
            self.__class__ = Fade_In
    def restart(self): self.start()
    def read(self):
        data = self.stream.read()
        if self.stream.true_progress + self.fade_settings()[1] >= self.stream.end_time or data.size == 0:
            self.__class__ = Fade_Out
        return data, self.volume
    def skip(self):
        self.stream.end_in(self.fade_settings()[1]*1000)
    @property
    def percent_progress(self) -> float:
        '''Returns a value between 0 and 1 representing the song's completion'''
        return self.stream.check_time() / ((self.stream.end_time - self.stream.pass_time)/1000)
    @property
    def progress_seconds(self) -> int:
        '''Returns the current temporal position of the song progress in seconds from 0'''
        return self.stream.check_time()
    @property
    def section_seconds(self) -> int:
        '''Returns the current temporal position of the song progress in seconds from start position'''
        return self.stream.check_time()

    def copy(self) -> Self:
        return Track(self.stream_creator,self.name,self.artist,self.image,self.album,self.year,self.volume,self.fade_settings,self.fade_function)

    @classmethod
    def _verify_and_apply_section(cls, stream_url: str, limits: tuple[float, float], duration, min_dur: int, **song_info) -> Self:
        '''Generates a song object from a stream, start/end limits, duration of the audio, minimum duration (fade times added), and song info.'''
        
        if max(min_dur,1) > duration: raise ValueError(f'Audio source must be at least {max(min_dur,1)} seconds in length.')
        
        end = int(round_to_frame(1000*(duration if limits[1] < 0 else max(min(limits[1],duration),1))))
        start = int(round_to_frame(1000*(min(max(limits[0],0), end-1))))
        kwargs: dict = OPTS.FFMPEG.copy()
        kwargs['options'] = kwargs['options'] + f' -ss {start/1000.}'
        kwargs.update({'pass_time':start,'end_time':end})
        def sc(): return ProgressibleFFmpegPCMAudio(stream_url, **kwargs)
        return Track(sc, **song_info)

    @classmethod
    def from_yt(cls, url: str, limits: tuple[float, float] = (0.0,-1.0), min_dur: int = 5, volume: float = 1.0, fade_settings: Callable[[],tuple[int, int]] = lambda: (0,0)) -> Self:
        with yt_dlp.YoutubeDL(OPTS.YTDLP) as ydl:
            song_info = ydl.extract_info(url, download=False)
            durtn = song_info['duration']
            surl = song_info['url']
            try:
                name = song_info['track']
                artist = song_info['artist']
                album = song_info['album']
                year = song_info['release_year']
            except KeyError:
                name = song_info['title']
                artist = song_info['channel']
                album = None
                try: year = int(song_info['release_date'][:4])
                except: year = None

            return cls._verify_and_apply_section(surl, limits, durtn, min_dur, 
                                            name = name, artist = artist,
                                            album = album, year = year,
                                            image = song_info['thumbnail'],
                                            volume = volume, fade_settings = fade_settings)
    @classmethod
    def from_file(cls, file_location: str, limits: tuple[float, float] = (0.0,-1.0), min_dur: int = 5, volume: float = 1.0, fade_settings: Callable[[],tuple[int, int]] = lambda: (0,0)) -> Self:
        match file_location:
            case x if len(x) < 5: raise ValueError("Filename invalid: Too Short")
            case x if x[-4:] == '.mp3':     fi = mp3.MP3(x)
            case x if x[-4:] == '.wav':     fi = wave.WAVE(x)
            case x if x[-5:] == '.aiff':    fi = aiff.AIFF(x)
            case x if x[-4:] == '.aac':     fi = aac.AAC(x)
            case x if x[-4:] == '.ogg':     fi = ogg.OggFileType(x)
            case _: raise ValueError("Filetype invalid: Must be: .mp3, .wav, .aiff, .aac, or .ogg")
        durtn = fi.info.length
    
        return cls._verify_and_apply_section(file_location, limits, durtn, min_dur,
                                name = fi['TIT2'][0], artist = fi['TPE1'][0],
                                album = fi['TALB'][0], year = int(fi['TDRC'][0]),
                                image = None,
                                volume = volume, fade_settings = fade_settings)
class Fade_In(Track):
    '''A song that is currently fading in (for internal use)'''
    def read(self):
        self.fade_progress += 20
        data = self.stream.read()
        m = self.fade_function(self.fade_progress, self.fade_settings()[0])
        if self.fade_progress >= self.fade_settings()[0]:
            self.__class__ = Track
        return data, m * self.volume
class Fade_Out(Track):
    '''A song that is currently fading out (for internal use)'''
    def read(self):
        data = self.stream.read()
        m = self.fade_function(self.stream.end_time - self.stream.true_progress, self.fade_settings()[1])
        return data, m * self.volume

class QueueNode:
    def __init__(self, prevnode: Self | None = None, nextnode: Self | None = None):
        self._prv: Self | None = prevnode
        self._nxt: Self | None = nextnode
        self.lock = threading.Lock()

        if self._prv:
            with self._prv.lock: self._prv._nxt = self
        if self._nxt:
            with self._nxt.lock: self._nxt._prv = self
    def insert(self, node: Self | Track):
        with self.lock: prv = self._prv
        if isinstance(node, Track):
            node = TrackNode(node, prv, self)
        else:
            with node.lock:
                node._prv = prv
                node._nxt = self
        if prv:
            with prv.lock: prv._nxt = node
        with self.lock: self._prv = node

    def append(self, node: Self | Track):
        with self.lock: nxt = self._nxt
        if isinstance(node, Track):
            node = TrackNode(node, self, nxt)
        else:
            with node.lock: 
                node._nxt = nxt
                node._prv = self
        if nxt:
            with nxt.lock: nxt._prv = node
        with self.lock:
            self._nxt = node
    def remove(self):
        with self.lock:
            del self.track
            n = self._nxt
            p = self._prv
            if n:
                with n.lock:
                    n._prv = p
            if p:
                with p.lock:
                    p._nxt = n
        del self
    def replace(self, node: Self| Track) -> Self:
        with self.lock:
            n = self._nxt
            p = self._prv
        if isinstance(node, Track):
            node = TrackNode(node, p, n)
        else:
            node._nxt = n
            node._prv = p
        if n: 
            with n.lock: n._prv = node
        if p: 
            with p.lock: p._nxt = node
        return node
    
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
    
    def end_of_playlist(self, repeat: int) -> Self | None:
        if repeat not in [REPEAT.PLA,REPEAT.PLM]: repeat = REPEAT.PLM
        n = self
        while(n._nxt):
            n = n._nxt
            if isinstance(n, PlaylistDelimiter) and n.repeat_setting == repeat:
                while (isinstance(n._nxt,PlaylistDelimiter)): n = n._nxt
                return n
            
        return None
class TrackNode(QueueNode):
    def __init__(self, track: Track, prevnode: QueueNode | None = None, nextnode: QueueNode | None = None):
        super().__init__(prevnode,nextnode)
        self.track = track
    def getnext(self, repeat_setting = 0):
        if repeat_setting == 1:
            return self.replace(self.track.copy())
        return super().getnext(repeat_setting)
class PlaylistDelimiter(QueueNode):
    def __init__(self,return_to_node_with_setting: tuple[int,TrackNode], max_repeats: int = -1, repeat_regardles:bool = False, prevnode: QueueNode | None = None, nextnode: QueueNode | None = None):
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
                 default_fade: tuple[float,float] = 0.0, read_func: bool | Callable = True) -> None:
        self.volume = volume
        self.repeat = repeat
        self.fade = default_fade
        
        self.writer = threading.Thread(target=self.write,name="Track Queue Audio Bufferer")
        self.cmder  = threading.Thread(target=self.accept_commands,name="Track Queue Command Accepter")
        self.queuer = threading.Thread(target=self.queue,name="Track Queuer")
        self.logic  = threading.Thread(target=self.track_start_end_logic,name="Track")

        # Resources that belong to the writer thread:
        self.current: deque[TrackNode] = deque([])
        self.history: deque[TrackNode] = deque([])


        #shared resources
        self.loop = asyncio.new_event_loop()
        self.start: TrackNode | None = None
        self.end: QueueNode | None = None
        self.stop = threading.Event()
        self.paused = False
        self.buffer = SingleBufferedAudio()
        self.add_track_queue: Queue[Callable[[],Track] | QueueNode] = Queue()
        self.command_queue: Queue[str] = Queue()

        # finish setting up
        self.writer.start()
        self.cmder.start()
        self.queuer.start()
        self.logic.start()
        if isinstance(read_func, bool):
            self.read = self.read_bytes if read_func else self.read_np_array
        else:
            self.read = read_func

    def read(self): pass 
    '''overwritten in __init__, subclass may implement by passing a callable read_func parameter to __init__ or by assinging self.read after super().__init__ is called'''
    def close(self):
        self.stop.set()
        n = self.start
        while(n):
            n.track.stream.end()
            n = n._nxt
        self.add_track_queue(QueueNode())
        self.writer.join()
        self.cmder.join()
        self.queuer.join()
        self.logic.join()
    def read_np_array(self):
        if self.paused: return ZERO_FRAME.copy()
        return self.buffer.read().astype(np.int16)
    def read_bytes(self):
        return self.read_np_array().tobytes()
    def write(self):
        while(not self.stop.is_set()):
            data = ZERO_FRAME_FLOAT.copy()
            for node in list(self.current):
                if node.track.stream and node.track.stream.source_progress > 0:
                    inp = node.track.read()
                    if inp[0].shape[0] > 0:
                        data += inp[0].astype(np.float64) * inp[1] * self.volume
                    else:
                        if node not in self.history:
                            self.add_track_history(node)
                        self.current.remove(node)
                        
            self.buffer.write(data)
    def add_new_track(self,node):
        if node in self.current:
            self.current.append(self.current.pop(self.current.index(node)))
        else: 
            self.current.append(node)
            node.track.start()
    def add_track_history(self,node):
        if node in self.history:
            i = len(self.history) - self.history.index(node)
            self.history.rotate(i)
        else: self.history.append(node) 
    def track_start_end_logic(self):
        while(not self.stop.is_set()):
            if self.current:
                now_playing = self.current[-1]
                nxt = now_playing.getnext(self.repeat)                              # IF THERE ARE ONE OR MORE CURRENTLY PLAYING SONGS:]
                if (nxt):                                                           # -> IF the most recent track has a track following it in the queue:
                    tte: int = now_playing.track.stream.time_to_end                 # -> -> find the playing track's time till end
                    if (tte < now_playing.track.fade_settings()[1] 
                        and now_playing not in self.history):
                        self.add_track_history(now_playing)
                        with nxt.lock:                                              # -> -> lock the following track
                            b = nxt.track.fade_settings()[0] >= tte                 # -> -> IF the following track can start fading in:
                        if b: self.add_new_track(nxt)                               # -> -> -> add it to the queue
                elif (self.repeat == 4 and self.start):                             # -> IF the most recent track is the end of the queue and repeat-all is on
                    self.add_new_track(self.start)                                  # -> -> add the song from the beginning of the queue again
                #await asyncio.sleep(FRAMELENSEC)                                   # -> Wait one audio frame before looping
            else:                                                                   # IF THERE ARE NO CURRENTLY PLAYING SONGS:
                if self.history:                                                    # -> IF there is a history of tracks
                    t = self.history[-1].getnext(self.repeat)                       # -> -> IF the latest addition to the history has a new following track in the queue
                    if t: self.add_new_track(t)                                     # -> -> -> add that following track to the currently playing list
                elif self.start: self.add_new_track(self.start)                     # -> IF the queue is new and a song has been added: add it to the currently playing songs
            sleep(0.02)                                                             # Wait a fifth of a second
    def queue(self):
        def add_node_or_playlist():
            toadd = self.add_track_queue.get()
            #playlist
            if isinstance(toadd,dict):
                if len(toadd['i']) > 0:
                    s1 = TrackNode(toadd['i'][0](),prevnode=self.end)
                    n = s1
                    for t in toadd['i'][1:]: n = TrackNode(t(),prevnode=n)
                    s2 = TrackNode(toadd['m'][0](),prevnode=n)
                else:
                    s1 = s2 = TrackNode(toadd['m'][0](),prevnode=self.end)
                n = s2
                for t in toadd['m'][1:]: n = TrackNode(t(),prevnode=n)
                n = PlaylistDelimiter((REPEAT.PLM,s2),toadd['mrm'],toadd['rrm'],prevnode=n)
                for t in toadd['o']: n = TrackNode(t(),prevnode=n)
                n = PlaylistDelimiter((REPEAT.PLA,s1),toadd['mrw'],toadd['rrw'],prevnode=n)
                self.end = n
            # single track
            else:
                if callable(toadd): toadd = TrackNode(toadd(),prevnode=self.end)
                elif isinstance(toadd,TrackNode):
                    if self.end != None: self.end.append(toadd)
                    else: self.end = toadd
        
        add_node_or_playlist()
        self.start = self.end.getbeginning()
        while(not self.stop.is_set()): 
            add_node_or_playlist()
            sleep(0.2)

    def accept_commands(self):
        def skip(): 
            if self.current: self.current[-1].track.skip()
        def skip_playlist():
            if self.current and (p := self.current[-1].end_of_playlist(self.repeat)):
                self.current[-1].track.skip()
                self.add_track_history(self.current[-1])
                if p._nxt: self.add_new_track(p._nxt)
                else: self.add_track_history(p)
        def rewind():
            if self.current:
                if self.current[-1].track.stream.true_progress > 3000:
                    self.current[-1].track.restart()
                else:
                    if self.history:
                        i = -1
                        while(isinstance(self.history[i],PlaylistDelimiter)): i = i -1
                        self.add_new_track(self.history[i])
                        self.current[-1].track.skip()
                    else:
                        self.current[-1].track.restart()
                    
            elif self.history:
                i = -1
                while(isinstance(self.history[i],PlaylistDelimiter)): i = i -1
                self.add_new_track(self.history[i])
        def pause(): self.paused = True
        def resume(): self.paused = False
        def volume(vol: float): self.volume = vol
        def repeat(set: int): self.repeat = set
        def fade_setting(set1: float, set2: float): self.fade = (set1, set2)
        while(not self.stop.is_set()):
            command: str = self.command_queue.get()
            l = command.split(' ',3)
            des = l[0]
            match des:
                case "skip": skip()
                case "skip_playlist": skip_playlist()
                case "rewind": rewind()
                case "pause": pause()
                case "resume": resume()
                case "volume": volume(float(l[1]))
                case "repeat": repeat(int(l[1]))
                case "fade": fade_setting(float(l[1]),float(l[2]))
    
    def get_add_song_func(self, location:str, limits:tuple[float,float] = (0.,-1.), volume: float = 1.0, fade_settings: tuple[float,float] | None = None):
        true_fade_settings = (int(s*1000) for s in fade_settings) if fade_settings and (fade_settings[0] or fade_settings[1]) else (lambda: self.fade)
        gen = Track.from_file if '.' in location[-5:] else Track.from_yt
        def f(): return gen(location,limits, volume=volume, fade_settings=true_fade_settings)
        return f

    def add_song_to_queue(self, location:str, limits:tuple[float,float] = (0.,-1.), volume: float = 1.0, fade_settings: tuple[float,float] | None = None):
        self.add_track_queue.put(self.get_add_song_func(location,limits,volume,fade_settings))
    
    def add_playlist_to_queue(self, intro: list[dict], main:  list[dict], outro: list[dict], 
                              max_repeats_main: int = -1, repeat_regardless_main: bool = False,
                              max_repeats_whole: int = -1, repeat_regardless_whole: bool = False):
        lg = lambda x: [self.get_add_song_func(**track) for track in x]
        i = lg(intro)
        m = lg(main)
        o = lg(outro)
        self.add_track_queue.put({'i':i,'m':m,'o':o,'mrm':max_repeats_main,'rrm':repeat_regardless_main,'mrw':max_repeats_whole,'rrw':repeat_regardless_whole})

    def command(self, command: str):
        '''
        sends a command to the writer thread that modifies the queue
        command -- one of the following strings: skip, skip_playlist, rewind, pause, resume, volume x.x, repeat x, fade x.x x.x
        '''
        self.command_queue.put(command)
    
    @property
    def currently_playing(self) -> TrackNode | None:
        if self.current: return self.current[-1]
        return None
        


#TODO: echo, reverb, muffling?