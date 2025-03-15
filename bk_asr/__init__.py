from .BcutASR import BcutASR
from .JianYingASR import JianYingASR

__all__ = ["BcutASR", "JianYingASR"]

def transcribe(audio_file, platform):
    assert platform in __all__
    asr = globals()[platform](audio_file)
    return asr.transcribe()
