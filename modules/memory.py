#!/usr/bin/env python
# -*- coding: utf-8 -*-
from modules import Timer, BUSY


class Memory:
    def __init__(self, data=[]):
        self._data = data
        self.transferTime = 3
        self.blocked = False
        self.reqLoc = None
        self.reqTimer = Timer()
        self.type = None
        self.requestee = None
        self.clock = 0
        self.servedTime = -1

    def lock(self, requestee):
        if not self.blocked:
            self.requestee = requestee
            return True
        else:
            return BUSY

    def read(self, loc, requestee=None):
        # Can only serve one per cycle
        if self.servedTime == self.clock:
            return BUSY

        if (not self.blocked and (self.requestee is None or
            (self.requestee == requestee and (self.type != 'R' or
             self.reqLoc != loc)))):
            self.requestee = requestee
            self.type = 'R'
            self.reqLoc = loc
            self.blocked = not self.reqTimer.tick(self.transferTime)

        if self.requestee == requestee:
            print ('Memory Read Access, Current timer: ' +
                   str(self.reqTimer.timer))

        if not self.blocked and self.requestee == requestee:
            self.reqLoc = None
            self.type = None
            self.requestee = None
            self.servedTime = self.clock
            return self._data[loc]

        return BUSY

    def write(self, loc, data, requestee=None):
        # Can only serve one per cycle
        if self.servedTime == self.clock:
            return BUSY

        if (not self.blocked and (self.requestee is None or
            (self.requestee == requestee and (self.type != 'W' or
             self.reqLoc != loc)))):
            self.type = 'W'
            self.reqLoc = loc
            self.requestee = requestee
            self.blocked = not self.reqTimer.tick(self.transferTime)

        if self.requestee == requestee:
            print('Memory Write Access, Current timer: ' +
                  str(self.reqTimer.timer))

        if not self.blocked and self.type == 'W' and self.reqLoc == loc:
            self.reqLoc = None
            self.type = None
            self.requestee = None
            self._data[loc] = data
            self.servedTime = self.clock
            return True

        return BUSY

    def getRawMem(self):
        return self._data

    def tick(self, clock):
        self.clock = clock
        self.blocked = not self.reqTimer.tick()
