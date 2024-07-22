from circularlist import CircularList, REOC_SEND_DEF
from io import BufferedIOBase
from discord import PCMAudio, PCMVolumeTransformer

FRAMSIZE = 3840
EMPTY_FRAME = bytes(FRAMSIZE)

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
    
    def read(self):
        val = (self.circlist.pop() if len(self) > self.target_size 
               else self.circlist.read(REOC_SEND_DEF))
        return val + bytes(FRAMSIZE-len(val))

    def write(self,data : bytes):
        if len(self) < self.target_size:
            return self.circlist.prepend_new_nodes(data)
        return self.circlist.write()

class SongQueue(CircularList):
    def __init__(self):
        super().__init__()
        