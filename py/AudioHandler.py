from circularlist import CircularList
from io import BufferedIOBase
from discord import PCMAudio, PCMVolumeTransformer

FRAMSIZE = 3840
EMPTY_FRAME = bytes(FRAMSIZE)

class CircularAudioBuffer(BufferedIOBase):
    def __init__(self, extra_audio_frames: int = 0) -> None:
        super().__init__()
        self.target_size = max(extra_audio_frames,0) + 1
        self.circlist = CircularList(self.target_size)
        

    def read(self):
        return self.circlist.read()
    def write(self):
        return self.criclist.write()