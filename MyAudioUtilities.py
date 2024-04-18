from pycaw.pycaw import AudioUtilities
import comtypes
from comtypes import CLSCTX_ALL
from pycaw.constants import CLSID_MMDeviceEnumerator
from pycaw.pycaw import (
    AudioUtilities,
    IAudioEndpointVolume,
    IMMDeviceEnumerator,
    EDataFlow,
    ERole,
)
from ctypes import POINTER, cast


class MyAudioUtilities(AudioUtilities):
    @staticmethod
    def GetSpeaker(id_=None):

        device_enumerator = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
        )
        if id_ is not None:
            speakers = device_enumerator.GetDevice(id_)
        else:
            speakers = device_enumerator.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eMultimedia.value)
        return speakers
