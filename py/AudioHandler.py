import math, asyncio, yt_dlp
import numpy as np
from circularlist import CircularList, REOC
from io import BufferedIOBase
from discord import FFmpegPCMAudio, PCMVolumeTransformer
from mutagen import mp3, wave, aiff, aac, ogg
from types import SimpleNamespace
from typing import IO, Callable
from time import time, sleep


FRAMESIZE = 3840                        # Length of an audio frame in bytes
ZERO_FRAME = bytes(FRAMESIZE)           # A placeholder audio frame of silence
FRAMELENMS: int = 20                   # Length of an audio frame in ms
FRAMELENSEC: float = FRAMELENMS/1000   # Length of an audio frame in s
DATAMINMAX: tuple[int,int]  = -(2**15), 2**15-1

def round_to_frame(num: int) -> int:
    return round(num/FRAMELENMS)*FRAMELENMS

def multiply_int16_bytes(bb: bytes, f:float ):
    data = np.frombuffer(bb,'int16')
    return (data * f)

def multiply_int16_bytes_a(bb: bytes, f: np.array[float] ):
    data = np.frombuffer(bb,'int16')
    return np.prod(data, f,axis=0)

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
class CircularAudioBuffer(BufferedIOBase):
    def __init__(self, extra_audio_frames: int = 0) -> None:
        super().__init__()
        self.target_size: int = max(extra_audio_frames,0) + 1
        self.circlist: CircularList = CircularList(self.target_size)
        self.rh = self.readhelper()
    
    def resize(self,size):
        self.target_size = max(size, 0) + 1
    def __len__(self):
        return len(self.circlist)
    def readable(self) -> bool:
        return True
    def writable(self) -> bool:
        return True
    
    def read(self,reoc_behav: int = REOC.WAIT, pad: bool = True) -> bytes:
        val = (self.circlist.pop() if len(self) > self.target_size
               else self.circlist.read(reoc_behav,bytes())) 
        return val + bytes((FRAMESIZE-len(val))*pad)

    def write(self,data : bytes):
        if len(self) < self.target_size:
            return self.circlist.prepend_new_nodes([data])
        return self.circlist.write()
class ProgessibleFFmpegPCMAudio(FFmpegPCMAudio):
    def __init__(self, source: str | BufferedIOBase, *, executable: str = 'ffmpeg', pipe: bool = False, stderr: IO[bytes] | None = None, before_options: str | None = None, options: str | None = None, pass_time: int = 0, end_time: int = -1) -> None:
        '''
        :int pass_time: What time in the source the audio should jump to at the start
        :int end_time: What time in the source the audio should stop at, if not the end'''
        super().__init__(source, executable=executable, pipe=pipe, stderr=stderr, before_options=before_options, options=options)
        self.progress = 0
        self.end_time = end_time
        self.pass_time = pass_time

    def read(self) -> bytes:
        if self.end_time > 0 and self.progress + self.pass_time >= self.end_time: 
            super().cleanup()
            return b''
        self.progress += 20
        return super().read()
    
    def check_time(self) -> float:
        return (self.progress + self.pass_time) / 1000

class Song():
    def __init__(self, stream_creator: Callable[[],ProgessibleFFmpegPCMAudio], duration: int, start: int, end: int, volume: float = 1.0) -> None:
        self.stream_creator: Callable[[],ProgessibleFFmpegPCMAudio] = stream_creator
        self.duration: duration
        self.volume = min(max(volume,1.0),0.001)

        self.stream: ProgessibleFFmpegPCMAudio
        self.start()

    def start(self) -> None:
        self.stream = self.stream_creator()
    def restart(self): self.start()
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

def verify_and_apply_section(stream_url: str, limits: tuple[float, float], duration, min_dur: int) -> Song:
    if max(min_dur,1) > duration: raise ValueError(f'Audio source must be at least {max(min_dur,1)} seconds in length.')
    end: float = round_to_frame(1000*(duration if limits[1] < 0 else max(min(limits[1],duration),1)))
    start: float = round_to_frame(1000*(max(min(math.ceil(limits[0] / FRAMELENSEC),0), end-1)))
    ffopts = OPTS.FFMPEG()
    ffopts['before_options'] = f'-ss {start}ms ' + ffopts
    sc = lambda: ProgessibleFFmpegPCMAudio(stream_url, **ffopts, pass_time=start, end_time=start)
    return Song(sc, duration, start, end)

def song_from_yt(url: str, limits: tuple[float, float] = (0.0,-1.0), min_dur: int = 5) -> Song:
    with yt_dlp.YoutubeDL(OPTS.YTDLP) as ydl:
        song_info = ydl.extract_info(url, download=False)
        durtn = song_info["duration"]
        surl = song_info["url"]
        return verify_and_apply_section(surl, limits, durtn, min_dur)
    
def song_from_file(file_location: str, limits: tuple[float, float] = (0.0,-1.0), min_dur: int = 5) -> Song:
    match file_location:
        case x if len(x) < 5:
            raise ValueError("Filename invalid: Too Short")
        case x if x[-4:] == '.mp3':
            fi = mp3.MP3(x).info
        case x if x[-4:] == '.wav':
            fi = wave.WAVE(x).info
        case x if x[-5:] == '.aiff':
            fi = aiff.AIFF(x).info
        case x if x[-4:] == '.aac':
            fi = aac.AAC(x).info
        case x if x[-4:] == '.ogg':
            fi = ogg.OggFileType(x).info
        case _:
            raise ValueError("Filetype invalid: Must be: .mp3, .wav, .aiff, .aac, or .ogg")
    durtn = fi.length
    return verify_and_apply_section(file_location, limits, durtn, min_dur)
    
class Playlist():
    def __init__(self, intro: list[Song] = [], main: list[Song] = [], outro: list[Song] = [], repeat_setting = REPEAT.OFF) -> None:
        self.list = [intro, main, outro]
        self.current = (-1,0)
        self.repeat = repeat_setting
    def change_repeat(self,repeat: int = REPEAT.OFF):
        self.repeat = repeat
    def skip(self) -> Song:
        if self.repeat == REPEAT.PLM and self.current[1] == 1:
            self.current = (-1,2)
        return self.next_song()

    def next_song(self) -> Song:
        match self.repeat:
            case REPEAT.OFF:
                pass #TODO
             
class SongQueue(CircularList):
    def __init__(self, volume: float = 1.0, repeat: int = REPEAT.OFF,
                 fadetime: float = 0.0, return_threshold: float = 3.0,
                 history_length: int = 10,) -> None:
        super().__init__()
        self.vol = volume
        self.rep = repeat
        self.fadetime = self.getfadeframes(fadetime)
        self.history: list[Song,list] = []
    
class FadeAudioWriter():
    def __init__(self, source: Callable[[],tuple[ProgessibleFFmpegPCMAudio | None,tuple[bool,bool]]], output_buffers: list[BufferedIOBase], fade_time : float | Callable[[],float] = 0.0) -> None:
        '''
        :Callable source: a function provided to a FadeAudioWriter instance that allows for changes in the stream. For normal use create a SongQueue object and pass its getstream function as this parameter.
        :float fade_time: How many seconds of crossfade to have.'''
        super().__init__()
        if not all([output_buffers.writable()]): raise TypeError("Audio writer's output buffer must be a writeable bufferto function.")
        self.fade_out: list[BufferedIOBase] = output_buffers                        # list of output buffers for multiple audio outputs

        self.source = source                                                        # stream souce function, aslo returns a bool if the stream has crossfading enabled
        self.stream: ProgessibleFFmpegPCMAudio                                      # current stream
        self.fade: tuple[bool,bool] = True, True                                    # boolean for current stream's crossfade enable/disable
        self.stream_available: asyncio.Event = asyncio.Event()                      # Event that must be set fy the stream provider when a new stream is available

        self.buffer1: CircularAudioBuffer | None                                    # Internal audio buffer for audio playback (fade in and non fade sections)
        self.buffer2: CircularAudioBuffer | None
        self.fade_time: Callable[[],float]
        self.set_fade_time(fade_time)
        

        self.task: asyncio.Task | None = None
        self.wait_task: asyncio.Task | None = None
        self.running: bool = False

    def set_fade_time(self, time: float | Callable[[],float]):
        match time:
            case Callable():
                self.fade_time = time
            case float():
                self.fade_time = lambda: time

    @property 
    def fade_second_vol_diff(self) -> float:
        ft = self.fade_time()
        return 1/ft if ft else 0

    @property
    def fade_b1_multipliers(self) -> np.array[float]:
        diff = self.fade_second_vol_diff
        prog = self.stream.progress / 1000
        s, e = max(prog - FRAMELENSEC,0.0) * diff, min(prog,1.0) * diff
        return np.linspace(s,e,FRAMESIZE)

    @property
    def fade_b2_multipliers(self) -> np.array[float]:
        diff = self.fade_second_vol_diff
        prog = len(self.buffer2) * FRAMELENSEC / self.fade_time()
        s, e = prog * diff, max(prog - FRAMELENSEC,0.0) * diff
        return np.linspace(s,e,FRAMESIZE)
    
    async def audio_in(self) -> bytes:
        if not self.stream:
            await self.wait_for_stream()
        if self.a#TODO
        data: bytes = self.stream.read()
        if not data: 
            del self.stream
            if self.fade[1]:
                del self.buffer2
                self.buffer2 = self.buffer1
                del self.buffer1
                self.buffer1 = CircularAudioBuffer(int(self.fade_time() / FRAMELENSEC))

        self.buffer1.write(data)

    async def audio_out(self):
        fade_cond = ((self.stream.progress - FRAMELENMS) / 1000 <= self.fade_time()
                     if self.stream else False)
        data1 = self.buffer1.read() if self.buffer1 else None
        data2 = None

        if self.buffer2: 
            l = len(self.buffer2)
            data2 = self.buffer2.read()
            if l == 1: del self.buffer2
            if self.fade:
                data2 = multiply_int16_bytes_a(data2, self.fade_b2_multipliers)

        data1 = (multiply_int16_bytes_a(data1,self.fade_b1_multipliers)
                if fade_cond and self.fade[0] else (np.frombuffer(data1,'int16')
                    if data1 and data2 else data1))
        
        match data1, data2:
            case x, y if x and y:
                sum = np.clip(x + y, DATAMINMAX[0], DATAMINMAX[1])
                outdata = bytes(sum.astype('int16'))
            case x, y if x and not y:
                outdata = bytes(x.astype('int16'))
            case x, y if (not x) and y:
                outdata = bytes(y.astype('int16'))
            case bytes(), None:
                outdata = data1
            case None, None:
                outdata = ZERO_FRAME
            case _:
                raise RuntimeError("Unkown fading case occured.")
            
        for buffer in self.fade_out:
            buffer.write(outdata)
    
    async def wait_for_stream(self):
        if self.
        self.stream, self.fade = self.source()
        while not self.stream:
            self.stream_available.clear()
            await self.stream_available.wait()
            self.stream, self.fade = self.source()

    async def main_loop(self) -> float:
        t = time()
        try:
            while self.running:
                if self.fade[1]:
                    if self.buffer1.target_size > len(self.buffer1):
                        await self.audio_in()
                    await self.audio_in()
                    await self.audio_out()
                if not self.fade[1]:

        except asyncio.CancelledError:
            raise
        finally:
            del self.stream, self.buffer1, self.buffer2
            return time() - t


    def stop(self) -> float:
        if self.running_co:
            self.running = False
            sleep(5)
            self.task.cancel()
            out = asyncio.wait_for(self.task)
            del self.task
            print("Audio writer coroutine stopped.")
            return out
        else:
            raise RuntimeError("Audio writer coroutine not started.")
        
    def start(self):
        if not self.running_co:
            self.task = asyncio.create_task(self.main_loop())
            self.running = True
            print("Audio writer coroutine started.")
        else:
            raise RuntimeError("Audio writer coroutine already started.")