#!/usr/bin/env python
# -*- coding: utf-8 -*-
from modules import Timer, BUSY, BANDWIDTH
import math
import copy


class Cache:
    def __init__(self, mem):
        self.mem = mem
        self.localMem = []
        self.tagMask = pow(2, BANDWIDTH) - 1
        self.indexMask = 0
        self.offsetMask = 0
        self.noOfSets = 0
        self.noOfBlocks = 0
        self.setSize = 0
        self.blockSize = 0
        self.clock = 0
        self.hitTime = 1

        self.blocked = False
        self.reqLoc = None
        self.reqTimer = Timer()
        self.requestee = None
        self.missStage = {'stage': 'EVICT', 'loc': 0}
        self.memFetchLoc = None
        self.noOfHits = 0
        self.noOfMiss = 0

    def config(self, noOfBlocks, blockSize, setSize=1):
        self.setSize = setSize
        self.noOfSets = noOfBlocks / self.setSize
        self.noOfBlocks = noOfBlocks
        self.blockSize = blockSize
        offsetBits = 0
        indexBits = 0

        while pow(2, offsetBits) < blockSize:
            offsetBits += 1

        while pow(2, indexBits) < noOfBlocks:
            indexBits += 1

        self.offsetMask = (1 << offsetBits) - 1
        self.indexMask = ((1 << indexBits) - 1) << offsetBits
        self.tagMask = self.tagMask & ~(self.indexMask | self.offsetMask)
        for i in range(0, self.noOfSets):
            cSet = []
            for j in range(0, self.setSize):
                cSet.append({'tag': None, 'dirty': False, 'words': []})
            self.localMem.append(cSet)

    def tick(self, clock):
        self.clock = clock
        self.blocked = not self.reqTimer.tick()

    def fetchBlock(self, loc, requestee, data=None):
        location = self.memFetchLoc or loc
        offset = location % self.blockSize
        index = (location / self.blockSize) % self.noOfSets
        tag = location / (self.blockSize * self.noOfSets)

        cSet = self.localMem[index]

        block = None
        for blk in cSet:
            if blk['tag'] == tag:
                block = blk
                break

        if self.requestee is not None and self.requestee != requestee:
            return BUSY

        # hit
        if self.memFetchLoc is None and block is not None:
            if self.requestee is None:
                self.requestee = requestee
                self.blocked = not self.reqTimer.tick(self.hitTime)

            if requestee == self.requestee and not self.blocked:
                self.requestee = None

                # LRU
                cSet.remove(block)
                cSet.insert(0, block)

                self.noOfHits += 1
                if data is None:
                    return block['words'][offset]
                else:
                    block['words'][offset] = data
                    block['dirty'] = True
                    return True
            else:
                return BUSY

        # miss
        else:
            if self.requestee is None:
                self.requestee = requestee

            if self.memFetchLoc is None:
                self.memFetchLoc = loc

            self.blocked = not self.reqTimer.tick(1)

            evictBlock = cSet[-1]
            # write if dirty
            if (evictBlock['dirty'] and self.missStage['stage'] == 'EVICT' and
                    self.missStage['loc'] < self.blockSize):

                loc = ((evictBlock['tag'] << int(math.log(self.blockSize, 2) +
                       math.log(self.noOfSets, 2))) |
                       (index << int(math.log(self.blockSize, 2))) |
                       self.missStage['loc'])

                memResult = self.mem.write(
                    loc, evictBlock['words'][self.missStage['loc']],
                    requestee=self)

                self.missStage['loc'] += 1 if memResult != BUSY else 0
                if self.missStage['loc'] < self.blockSize:
                    self.mem.lock(self)
                return BUSY
            else:
                if self.missStage['stage'] == 'EVICT':
                    self.missStage = {'stage': 'FETCH', 'loc': 0}
                    evictBlock['tag'] = None
                    evictBlock['dirty'] = False
                    evictBlock['words'] = []

                if self.missStage['loc'] < self.blockSize:

                    loc = ((tag << int(math.log(self.blockSize, 2) +
                           math.log(self.noOfSets, 2))) |
                           (index << int(math.log(self.blockSize, 2))) |
                           self.missStage['loc'])

                    memResult = self.mem.read(loc, requestee=self)
                    if memResult != BUSY:
                        self.missStage['loc'] += 1
                        evictBlock['words'].append(memResult)
                        if self.missStage['loc'] < self.blockSize:
                            self.mem.lock(self)
                    return BUSY
                else:
                    self.missStage = {'stage': 'EVICT', 'loc': 0}
                    self.requestee = None
                    evictBlock['tag'] = tag

                    # LRU
                    cSet.pop(-1)
                    cSet.insert(0, evictBlock)

                    self.noOfMiss += 1

                    if loc != self.memFetchLoc:
                        self.memFetchLoc = None
                        return BUSY

                    self.memFetchLoc = None

                    if data is None:
                        return evictBlock['words'][offset]
                    else:
                        evictBlock['words'][offset] = data
                        evictBlock['dirty'] = True
                        return True

    def getMem(self):
        return self.mem.getRawMem()


# 2-way set associative, Four 4-words, LRU replacement
# Write-back strategy, write-allocate policy
class Dcache(Cache):
    def __init__(self, mem):
        Cache.__init__(self, mem)
        self.hitTime = 1

    def _getBlockAddress(self, loc):
        return loc % self.noOfBlocks

    def read(self, loc, requestee):
        print "D-Cache read (" + str(loc) + ")"
        return copy.deepcopy(self.fetchBlock(loc, requestee=requestee))

    def write(self, loc, data, requestee):
        print "D-Cache write (Loc: " + str(loc) + "): " + str(data)
        return self.fetchBlock(loc, data=data, requestee=requestee)


# Direct-mapped
class Icache(Cache):
    def __init__(self, mem):
        Cache.__init__(self, mem)
        self.hitTime = 1

    def _getBlockAddress(self, blockAddress):
        return (blockAddress / self.blockSize) % self.noOfBlocks

    def read(self, loc, requestee):
        print "I-Cache read (Loc: " + str(loc) + ")"
        return copy.deepcopy(self.fetchBlock(loc, requestee=requestee))
