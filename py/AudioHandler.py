from circularlist import CircularList
from io import BufferedIOBase
from discord import PCMAudio, PCMVolumeTransformer

FRAMSIZE = 3840
EMPTY_FRAME = bytes(FRAMSIZE)

class CircularAudioBuffer(BufferedIOBase):
    def __init__(self, extra_audio_frames: int = 0) -> None:
        super().__init__()
        self.target_size: int = max(extra_audio_frames,0) + 1
        self.circlist: CircularList = CircularList(self.target_size)
    
    def resize(self,size):
        self.target_size = max(size, 0) + 1
    def __len__(self):
        return len(self.circlist)
    
    def read(self):
        return self.circlist.read()
    
    def write(self):
        return self.circlist.write()