import threading, sys, asyncio, yt_dlp, aiologic
from os import path
import numpy as np
from io import BufferedIOBase
from discord import FFmpegPCMAudio, PCMAudio
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

path_to_ffmpeg = path.join(path.dirname(sys.executable),'ffmpeg\\bin\\ffmpeg.exe')
path_to_ffmpeg = path_to_ffmpeg if path.exists(path_to_ffmpeg) else path.join(path.dirname(path.dirname(__file__)),'dist\\ffmpeg\\bin\\ffmpeg.exe')
OPTS.FFMPEG = { 'executable': path_to_ffmpeg,
                'before_options':'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
                'options':'-vn -filter:a "volume=0.15"'}
OPTS.YTDLP = {'before_options':'-x','format':'bestaudio','quiet':True,'ignoreerrors':True}

def round_to_frame(n):
    '''Takes a number of miliseconds and rounds it to the nearest audio frame timing in ms'''
    return round(n*FRAMELENSEC,0) * FPS

class SingleBufferedAudio:
    def __init__(self):
        self.audio: np.ndarray = ZERO_FRAME.copy()
        self.w = threading.Event()
        self.r = threading.Event()
        self.__escaped = False
        self.w.set()

    def write(self, data: bytes | np.ndarray):
        '''Writes audio to the buffer supplied as a bytes object or np array of ints'''
        if isinstance(data,bytes):
            data = np.frombuffer(data,'int16')
        self.w.wait()
        if self.__escaped: return
        self.audio = data
        self.w.clear()
        self.r.set()

    def read(self) -> np.ndarray:
        '''Reads audio from the buffer'''
        self.r.wait()
        if self.__escaped: return np.ndarray([])
        data = self.audio
        self.r.clear()
        self.w.set()
        return data
    def escape(self):
        self.__escaped = True
        self.r.set()
        self.w.set()

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
        self.thread = threading.Thread(target=self.write)
        self.thread.start()
        
    def write(self):
        '''coroutine for writing audio from the source to the buffer'''
        while(self.end_time > 0 and self.source_progress + self.pass_time <= self.end_time):
            #print("Writing Audio")
            data = super().read()
            if len(data) == 0: break
            self.source_progress += 20
            self.raw_queue.write(data)
        self.raw_queue.write(np.array([]))        
    def end(self):
        self.raw_queue.escape()
        self.thread.join()
        super().cleanup()
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
                 album: str | None, year: int, volume: float = 1.0, fade_settings: tuple[Callable[[],int],Callable[[],int]] = (lambda: 0, lambda: 0),
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
        self.fade_in, self.fade_out = self.perm_in, self.perm_out = fade_settings  # Fade in/out timing in ms
        self.fade_progress: int = 0
        self.fade_function: Callable[[np.ndarray[Any,np.int16],float,float]
                                     ,np.ndarray[Any,np.int16]] = fade_function # Fade multiplier fuctio
        self.stream: Optional[ProgressibleFFmpegPCMAudio] = None
        self.ending: bool = False

    def start(self):
        if hasattr(self, 'stream'):
            del self.stream
        self.fade_in, self.fade_out = self.perm_in, self.perm_out
        self.ending = False
        self.stream = self.stream_creator()
    def restart(self): self.start()
    def read(self):
        data = self.stream.read()
        if data.size == 0:
            self.ending = True
            return data, 0.
        m: float | np.ndarray[np.float64] = self.volume
        match self.stream.true_progress, (self.stream.end_time - self.stream.pass_time), self.fade_in(), self.fade_out():
            case a,b,c,d if a+d >= b and d > 0:
                m *= self.fade_function(b-a,d)
                self.ending = True
            case a,b,c,d if a <= c:
                m *= self.fade_function(a,c)
        return data, m

    def skip(self):
        self.ending = True
        self.stream.end_in(min(self.fade_out(),self.stream.true_progress))
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
        return Track(self.stream_creator,self.name,self.artist,self.image,self.album,self.year,self.volume,(self.fade_in,self.fade_out),self.fade_function)

    @classmethod
    def _verify_and_apply_section(cls, stream_url: str, limits: tuple[float, float], duration, min_dur: int = 5, **song_info) -> Self:
        '''Generates a song object from a stream, start/end limits, duration of the audio, minimum duration (fade times added), and song info.'''
        
        if max(min_dur,1) > duration: raise ValueError(f'Audio source must be at least {max(min_dur,1)} seconds in length.')
        
        end = int(round_to_frame(1000*(duration if limits[1] < 0 else max(min(limits[1],duration),1))))
        start = int(round_to_frame(1000*(min(max(limits[0],0), end-1))))
        kwargs: dict = OPTS.FFMPEG.copy()
        kwargs['options'] = kwargs['options'] + f' -ss {start/1000.}'
        kwargs.update({'pass_time':start,'end_time':end})
        def sc(): return ProgressibleFFmpegPCMAudio(stream_url, **kwargs)
        return cls(sc, **song_info)
    @classmethod
    def yt_info(cls, url: str) -> dict:
        with yt_dlp.YoutubeDL(OPTS.YTDLP) as ydl:
            song_info = ydl.extract_info(url, download=False)
            if ('_type' in song_info.keys() and song_info['_type'] == 'playlist'): return song_info
            duration = song_info['duration']
            stream_url = song_info['url']
            image = song_info['thumbnail']
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
            return {'duration': duration, 'stream_url': stream_url, 'name': name, 'artist': artist, 'album': album, 'year': year, 'image': image}
    @classmethod
    def file_info(cls, file_location: str) -> dict:
        match file_location:
            case x if len(x) < 5: raise ValueError("Filename invalid: Too Short")
            case x if x[-4:] == '.mp3':     fi = mp3.MP3(x)
            case x if x[-4:] == '.wav':     fi = wave.WAVE(x)
            case x if x[-5:] == '.aiff':    fi = aiff.AIFF(x)
            case x if x[-4:] == '.aac':     fi = aac.AAC(x)
            case x if x[-4:] == '.ogg':     fi = ogg.OggFileType(x)
            case _: raise ValueError("Filetype invalid: Must be: .mp3, .wav, .aiff, .aac, or .ogg")
        return {'duration': fi.info.length, 'stream_url': file_location, 'name': fi['TIT2'][0], 'artist': fi['TPE1'][0], 'album': fi['TALB'][0], 'year': int(fi['TDRC'][0]), 'image': None}
    @classmethod
    def generate_track_func(cls,location: str, limits: tuple[float, float], **playback_info):
        if '.' in location[-5:]:
            info = cls.file_info(location)
        else:
            info = cls.yt_info(location)
        if '_type' in info.keys() and info['_type'] == 'playlist':
            playlist = {'i':[],'m':[],'o':[],'mrm':-1,'rrm':False,'mrw':-1,'rrw':False}
            playlist['m'] = [(lambda video=video: cls._verify_and_apply_section(**playback_info, stream_url=video['url'],limits=(-1.,-1.),duration=video['duration'],
                                                                                image=video['thumbnail'],
                                                                                name=(video['track'] if 'track' in video.keys() else video['title']),
                                                                                artist=(video['artist'] if 'artist' in video.keys() else video['channel']),
                                                                                year=(video['release_year'] if 'release_year' in video.keys() else video['release_date'][:4]),
                                                                                album=(video['album'] if 'album' in video.keys() else None))) for video in info['entries'] if video]
            return playlist
        return lambda: cls._verify_and_apply_section(**info, **playback_info, limits=limits)

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
        with self.lock: n = self._nxt
        if n.__class__ == PlaylistDelimiter:
            return n.getnext(repeat_setting)
        return n
    def getbeginning(self):
        with self.lock: p = self._prv
        if p == None: return self
        return p.getbeginning()
    def as_list(self):
        b = self.getbeginning()
        l = []
        while b:
            l.append(b)
            b = b._nxt
        return l
    def __contains__(self, item, s = True):
        with self.lock:
            n = self.getbeginning() if s else self._nxt
        return n.__contains__(item, s = False) if n else False
    
    def end_of_playlist(self, repeat: int) -> Self | None:
        if repeat not in [REPEAT.PLA,REPEAT.PLM]: repeat = REPEAT.PLM
        n = self
        l = []
        while(n._nxt):
            l.append(n)
            n = n._nxt
            if isinstance(n, PlaylistDelimiter) and (n.repeat_setting == repeat or n.repeat_setting == REPEAT.PLA) and n.return_node in l:
                return n
        return None
class TrackNode(QueueNode):
    def __init__(self, track: Track, prevnode: QueueNode | None = None, nextnode: QueueNode | None = None):
        super().__init__(prevnode,nextnode)
        self.track = track
    def getnext(self, repeat_setting = 0):
        if repeat_setting == REPEAT.ONE or (r := super().getnext(repeat_setting)) == self:
            r = self.replace(self.track.copy())
        return r
    def track_dict(self):
        t = self.track
        return {"type":"track","name":t.name,"artist":t.artist,"img":t.image,"year":t.year,"album":t.album}
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

class TrackQueue(PCMAudio):
    def __init__(self, volume: float = 1.0, repeat: int = REPEAT.OFF,
                 default_fade_in: float = 0.0, default_fade_out: float = 0.0,
                 read_func: bool | Callable = True) -> None:
        self.volume = volume
        self.repeat = repeat
        self.fade = default_fade_in , default_fade_out
        
        self.writer = threading.Thread(target=self.write,name="Track Queue Audio Bufferer")
        self.cmder  = threading.Thread(target=self.accept_commands,name="Track Queue Command Accepter")
        self.queuer = threading.Thread(target=self.queue,name="Track Queuer")

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

        self.update_playing = aiologic.SimpleQueue()
        self.update_queue = aiologic.SimpleQueue()

        # finish setting up
        self.writer.start()
        self.cmder.start()
        self.queuer.start()
        if isinstance(read_func, bool):
            self.read = self.read_bytes if read_func else self.read_np_array
        else:
            self.read = read_func

    def debug(self) -> str:
        d = self.as_dictionary()
        o =(f"Queue: {d['queue']}\n" +
            f"Current: {d['current']}\n" +
            f"History: {d['history']}\n" + 
            f"Repeat: {self.repeat}, Volume: {self.volume}\n" + 
            f"Paused: {self.paused}\n" +
            f"Threads:\n  Writer | Alive: {self.writer.is_alive()}\n  Queuer | Alive: {self.queuer.is_alive()}\n  Cmmder | Alive {self.cmder.is_alive()}\n" +
            f"Next: {self.current[-1].getnext(self.repeat)}")
        print(o)
        return o

    def read(self): pass 
    '''overwritten in __init__, subclass may implement by passing a callable read_func parameter to __init__ or by assinging self.read after super().__init__ is called'''
    def close(self):
        self.volume = 0.
        self.paused = False
        self.stop.set()
        for n in self.current:
            n.track.stream.end()
        self.add_track_queue.put(TrackNode(None))

        self.update_playing.put(self.currently_playing)
        self.update_queue.put(None)
        
        if self.buffer.r.is_set(): self.read()
        self.writer.join()
        self.command('end')
        self.cmder.join()
        self.queuer.join()
    def read_np_array(self):
        if self.paused: r = ZERO_FRAME.copy()
        else: r =self.buffer.read().astype(np.int16)
        return r
    def read_bytes(self):
        return self.read_np_array().tobytes()
    def write(self):
        while(not self.stop.is_set()):
            self.track_start_end_logic()
            data = ZERO_FRAME_FLOAT.copy()
            for node in list(self.current):
                if hasattr(node.track, 'stream') and node.track.stream:
                    inp = node.track.read()
                    if inp == None: continue
                    if inp[0].shape[0] > 0:
                        data += inp[0].astype(np.float64) * inp[1] * self.volume
                    else:
                        if node not in self.history:
                            self.add_track_history(node)
                        node.track.stream.end()
                        self.current.remove(node)
                        self.update_playing.put(self.currently_playing)
                        
            self.buffer.write(data)
    def add_new_track(self,node : QueueNode):
        """
        if isinstance(node,TrackNode) and node.track.ending == True:
            print("aaaaa")
            newnode = TrackNode(node.track.copy(),node._prv,node._nxt)
            if node == self.end: self.end = node = newnode
            else: node = newnode
            """
        if node in self.current:
            self.current.remove(node)
            node.track.restart()
            self.current.append(node)
        else: 
            self.current.append(node)
            node.track.start()
        self.update_playing.put(self.currently_playing)

    def add_track_history(self,node):
        if node in self.history:
            self.history.remove(node)
        self.history.append(node) 

    def track_start_end_logic(self):
        if self.current:
            now_playing = self.current[-1]
            nxt = now_playing.getnext(self.repeat)                              # IF THERE ARE ONE OR MORE CURRENTLY PLAYING SONGS:]
            if nxt is None and now_playing.track.ending and self.repeat == 4:
                self.start = nxt = TrackNode(self.start.track.copy(),None,self.start._nxt)
            if (nxt and hasattr(self.current, 'stream')):                       # -> IF the most recent track has a track following it in the queue:
                tte: int = now_playing.track.stream.time_to_end                 # -> -> find the playing track's time till end
                if (tte <= now_playing.track.fade_out()):
                    with nxt.lock:                                              # -> -> lock the following track
                        nxt.track.restart()
                        b = nxt.track.fade_in() >= tte                          # -> -> IF the following track can start fading in:
                    if b: self.add_new_track(nxt)                               # -> -> -> add it to the queue
        else:                                                                   # IF THERE ARE NO CURRENTLY PLAYING SONGS:
            if self.history:                                                    # -> IF there is a history of tracks
                t = self.history[-1].getnext(REPEAT.OFF)                        # -> -> IF the latest addition to the history has a new following track in the queue
                if t: self.add_new_track(t)                                     # -> -> -> add that following track to the currently playing list
            elif self.start: self.add_new_track(self.start)                     # -> IF the queue is new and a song has been added: add it to the currently playing songs=
    def queue(self):
        def add_node_or_playlist():
            while(True):
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
                    if callable(toadd):
                        try: 
                            toadd = TrackNode(toadd(),prevnode=self.end)
                            self.end = toadd
                        except: continue
                    elif isinstance(toadd,TrackNode):
                        self.end.append(toadd)
                        self.end = toadd
                break
        
        add_node_or_playlist()
        self.start = self.end.getbeginning()
        while(not self.stop.is_set()): 
            add_node_or_playlist()
            self.update_queue.put(None)
            sleep(0.5)
            

    def accept_commands(self):
        def nf(comm_func):
            curr_node, next_node = comm_func()
            if isinstance(curr_node,TrackNode): curr_node.track.stream.end_in(0)
            if isinstance(next_node,TrackNode): next_node.track.fade_in = lambda: 0

        def skip() -> tuple[Optional[TrackNode],Optional[TrackNode]]:
            i = 0
            c = n = None
            if len(self.current) > 0:
                while i < len(self.current) and list(self.current)[i].track.ending: i += 1
                try: c = self.current[i]
                except: return None, None
                c.track.skip()
                n = self.current[i].getnext(self.repeat)
                if n is not None:
                    self.add_new_track(n)
            return c, n
        def skip_playlist() -> tuple[Optional[TrackNode],Optional[TrackNode]]:
            c = n = None
            if self.current and (p := self.current[-1].end_of_playlist(self.repeat)):
                i = 0
                try: 
                    while self.current[i].track.ending: i += 1
                except: return
                c = self.current[i]
                c.track.skip()
                self.add_track_history(c)
                while isinstance(p._nxt,PlaylistDelimiter):
                    p = p._nxt
                    print(p)
                if p._nxt:
                    n = p._nxt
                    self.add_new_track(n)
                else: self.add_track_history(p)
            return c, n
                
        def rewind() -> tuple[Optional[TrackNode],Optional[TrackNode]]:
            playing = len(self.current) > 0
            progress = playing and self.current[-1].track.stream.true_progress > 3000
            history = len(self.history) > 0
            
            c = self.current[-1] if playing else None
            if isinstance(c,TrackNode): c.track.skip()
            n = None
            match playing, progress, history:
                case A,B,C if A and not (C and B):   # Restart track
                    n = TrackNode(c.track.copy(),c._prv,c._nxt)
                    self.add_new_track(n)
                case A,B,C if C and (B or not A):       # Play last track
                    i = -1
                    while(isinstance(self.history[i],PlaylistDelimiter)): i = i -1
                    n = self.history[i]
                    self.add_new_track(n)
            return c, n
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
                case "skip_nf": nf(skip)
                case "skip_playlist": skip_playlist()
                case "skip_playlist_nf": nf(skip_playlist)
                case "rewind": rewind()
                case "rewind_nf": nf(rewind)
                case "pause":  pause()
                case "resume": resume()
                case "volume": volume(float(l[1]))
                case "repeat": repeat(int(l[1]))
                case "fade":   fade_setting(float(l[1]),float(l[2]))
                case "end": break
                case _: continue
    
    def __get_add_song_func(self, location:str, start:float = 0., end:float = -1., volume: float = 1.0, fade_in: Optional[float] = None, fade_out: Optional[float] = None, pre_searched: bool = False, **track_info):
        def fmt(s,o): 
            if s and s > 0: f = lambda: int(s*1000)
            else: f = lambda: int(self.fade[o]*1000)
            return f
        true_fade_settings = fmt(fade_in,0), fmt(fade_out,1)
        track_info.update({'location':location,'limits':(start,end),'volume':volume,'fade_settings':true_fade_settings})
        gen = (lambda: Track._verify_and_apply_section(**track_info)) if pre_searched else Track.generate_track_func(**track_info)
        return gen

    def add_song_to_queue(self, location:str, start:float = 0., end:float = -1., volume: float = 1.0, fade_in: Optional[float] = None, fade_out: Optional[float] = None, pre_searched: bool = False):
        self.add_track_queue.put(self.__get_add_song_func(location,start,end,volume,fade_in,fade_out,pre_searched))
    
    def add_playlist_to_queue(self, intro: list[dict], main:  list[dict], outro: list[dict], 
                              max_repeats_main: int = -1, repeat_regardless_main: bool = False,
                              max_repeats_whole: int = -1, repeat_regardless_whole: bool = False):
        lg = lambda x: [self.__get_add_song_func(**track) for track in x]
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
    def currently_playing(self) -> list[dict]:
        return [tn.track_dict() for tn in self.current]
    @property
    def current_queue(self,q = []) -> list[dict]:
        if (self.repeat == REPEAT.ONE): return [self.current[-1].track_dict()] * 5
        if (len(self.current) > 0 and (n := self.current[-1].getnext(self.repeat) != None) and n not in q):
            return self.current_queue(q + [n.track_dict()] if isinstance(n,TrackNode) else q)
        return q
    
    def as_dictionary(self) -> dict:
        q = self.start.as_list() if self.start is not None else []
        d = {"queue": [n.track_dict() if isinstance(n,TrackNode) else {"type":"pd","link":str(q.index(n.return_node)) + ", name: " + str(n.return_node.track_dict()['name'])} for n in q]
            ,"current": [n.track_dict() for n in list(self.current)]
            ,"history": [n.track_dict() for n in list(self.history) if isinstance(n, TrackNode)]
            }
        return d

class DigitalAudioTransformer: pass
#TODO: echo, reverb, muffling?