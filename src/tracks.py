import os

import config as c

class Tracks:
    def __init__(self, audio):
        c.update()
        self.a = audio
        self.vocalTrackPos = 0
        self.playCount = 0
        self.vocalTrackLocation = c.VOCALS_DIR
        self.ambientTrackPos = 0
        self.ambientTrackLocation = c.AMBIENT_DIR
        self.tracksDic = {1:'01', 2: '02', 3: '03', 4: '04', 5: '05', 6: '06',
                          7: '07', 8: '08', 9: '09', 10: '10'}
        # Determine which, if any, files are present
        self.vocalList = []
        self.ambientList = []
        for i in range(1,11):
            vocalTrackFile = self.vocalTrackLocation+'v'+self.tracksDic[i]+'.wav'
            if os.path.isfile(vocalTrackFile):
                self.vocalList.append(i)
            ambientTrackFile = self.ambientTrackLocation+'a'+self.tracksDic[i]+'.wav'
            if os.path.isfile(ambientTrackFile):
                self.ambientList.append(i)

    def play_vocal(self):
        """Play the next vocal track, blocking until it finishes."""
        if self.vocalList != [] :
            vocalFileName = 'v'+self.tracksDic[self.vocalList[self.vocalTrackPos]]+'.wav'
            vocalTrackFile = self.vocalTrackLocation+vocalFileName
            self.a.play_track(vocalTrackFile, block=True)
            if self.vocalTrackPos == len(self.vocalList) - 1 :
                self.vocalTrackPos = 0
                self.playCount += 1
                print("Current play count" + str(self.playCount))
            else:
                self.vocalTrackPos += 1
            if self.playCount == 3 :
                raise SystemExit(1)

    def play_ambient(self):
        """Start the next ambient track (jaw not driven). Non-blocking:
        returns the completion event, or None if no tracks exist."""
        if self.ambientList != []:
            ambientFileName = 'a'+self.tracksDic[self.ambientList[self.ambientTrackPos]]+'.wav'
            ambientTrackFile = self.ambientTrackLocation+ambientFileName
            if self.ambientTrackPos == len(self.ambientList) - 1:
                self.ambientTrackPos = 0
            else:
                self.ambientTrackPos += 1
            return self.a.play_track(ambientTrackFile, block=False, drive=False)
        return None