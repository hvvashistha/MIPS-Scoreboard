# -*- coding: utf-8 -*-

import re
import copy
import math
import pdb

#Status Codes
BUSY = 'BUSY'
BANDWIDTH = 64
DATA_START = 64

class Inst:
    registers = ['Fi','Fj','Fk']

    def __init__(self, instruction, symbolList):
        self.inst = instruction
        instruction = instruction.replace(",", "")
        instruction =  re.split('\s+', instruction)
        self.cmd = instruction[0]
        self.stages = {}

        if self.cmd in ['BNE', 'BEQ', 'J'] and not instruction[-1].isdigit():
            instruction[-1] = str(symbolList[instruction[-1]])

        if self.cmd != 'HLT':
            for i in range(1, len(instruction)):
                setattr(self, Inst.registers[i-1], instruction[i])

    def mark(self, stage, value):
        if stage in ['WAW', 'RAW'] and value == 'Y':
            print 'Marking ' + self.inst + ' : ' + stage + ' ' + value
        if not hasattr(self.stages, stage):
            self.stages[stage] = value

    def val(self, reg, regValue = None):
        mem = False
        val = regValue
        if hasattr(self, reg):
            r = getattr(self, reg)
            if r.isdigit():
                val = int(r)
            else:
                disp = r.find('(')
                if disp > 0:
                    val = int(r[:disp]) + regValue
                    val = val / 4 #Word Align
                    mem = True

        if self.cmd == 'SW' and reg == self.registers[0]:
            val = '{:0>32b}'.format(int(val))[-32:]
        elif self.cmd == 'S.D' and reg == self.registers[0]:
            val = '{:0>64b}'.format(int(val))[-64:]

        return val, mem

    def reg(self, reg):
        r = []
        if hasattr(self, reg):
            r = re.findall('[R|F][0-9]+', getattr(self, reg))
        return r[0] if len(r) > 0 else None

#Registers {value, producer, consumer}
class Unit:
    def __init__(self, uType, regs, mem = None, execTime = 1, continuePipeline = None):
        self.busy = False
        self.type = uType
        self.memory = mem
        self.execTime = execTime
        self.continuePipeline = continuePipeline
        self.regs = regs
        self.clock = 0
        self.timer = Timer()
        self.currentStage = 0
        self.blocked = False
        self.stages = [None, self.issue, self.read, self.execute, self.write]
        self.Vi = None
        self.Vj = None
        self.Vk = None

    def Busy(self):
        return self.busy

    def _setNotBusy(self):
        self.busy = False
        self.blocked = False
        self.Vi = None
        self.Vj = None
        self.Vk = None
        self.Op = None
        self.currentStage = 0

    def operate(self, op):
        if op.find('ADD') >= 0:
            return self.Vj + self.Vk
        elif op.find('SUB') >= 0:
            return self.Vj - self.Vk
        elif op.find('AND') >= 0:
            return self.Vj & self.Vk
        elif op.find('OR') >= 0:
            return self.Vj | self.Vk

        elif op.find('ADD.D') >= 0:
            return float(self.Vj) + float(self.Vk)
        elif op.find('SUB.D') >= 0:
            return float(self.Vj) - float(self.Vk)
        elif op.find('MUL.D') >= 0:
            return float(self.Vj) * float(self.Vk)
        elif op.find('DIV.D') >= 0:
            return float(self.Vj) / float(self.Vk)
        elif op.find('LUI') >= 0:
            return self.Vj << 16
        elif op.find('L') >= 0:
            return self.Vj

    # def _result(self):
    def issue(self, inst = None, bookKeep = False, clock = None):
        if inst is None:
            print "Issue: " + str(self.clock)

        if clock is not None:
            self.clock = clock

        if bookKeep:
            self.Op.mark('ISSUE', self.clock)
            print self.Op.inst + " > IS (" + str(self.clock) + ")"
            if self.Op.cmd == 'J':
                self.continuePipeline(int(Fi))
                self._setNotBusy()
            return True

        Fi = inst.reg('Fi')
        Fj = inst.reg('Fj')
        Fk = inst.reg('Fk')

        if inst.cmd in ['SW', 'S.D', 'BEQ', 'BNE']:
            Fi = None
            Fj = inst.reg('Fi')
            Fk = inst.reg('Fj')

        if Fi is None or self.regs[Fi]['result'] is None:
            self.busy = True
            self.Op = inst

            if Fi is not None:
                self.regs[Fi]['result'] = {'type': self.type, 'clock': self.clock}

            if Fj is not None:
                self.regs[Fj]['source'].append(self.type)

            if Fk is not None:
                self.regs[Fk]['source'].append(self.type)

            self.currentStage = 0
            self.blocked = not self.timer.tick(1)
            return True
        else:
            inst.mark('WAW', 'Y')
            return False

    def read(self, bookKeep = False):
        print "Read: " + str(self.clock)

        i = 'Fi'; j = 'Fj'; k = 'Fk';

        if self.Op.cmd in ['SW', 'S.D', 'BEQ', 'BNE']:
            k = j; j = i;

        Fj = self.Op.reg(j); Fk = self.Op.reg(k);

        if not bookKeep:
            val = None
            self.blocked = False
            if self.Vj is None or self.Vj == BUSY:
                if Fj is None:
                    self.Vj, mem = self.Op.val(j)
                elif (self.regs[Fj]['result'] is None or self.regs[Fj]['result']['type'] == self.type or
                        self.regs[Fj]['result']['clock'] == self.clock):

                    val = self.regs[Fj]['value']
                    self.Vj, mem = self.Op.val(j, val)
                else:
                    self.Op.mark('RAW', 'Y')
                    self.blocked = True

            if self.Vk is None or self.Vk == BUSY:
                if Fk is None:
                    self.Vk, mem = self.Op.val(k)
                elif (self.regs[Fk]['result'] is None or self.regs[Fk]['result']['type'] == self.type or
                        self.regs[Fk]['result']['clock'] == self.clock):
                    val = self.regs[Fk]['value']
                    self.Vk, mem = self.Op.val(k, val)
                else:
                    self.Op.mark('RAW', 'Y')
                    self.blocked = True

        elif not self.blocked:
            if Fj is not None:
                try:
                    self.regs[Fj]['source'].remove(self.type)
                except ValueError:
                    pdb.set_trace()
            if Fk is not None:
                try:
                    self.regs[Fk]['source'].remove(self.type)
                except ValueError:
                    pdb.set_trace()

            if (self.Op.cmd == 'BEQ' and self.Vj == self.Vk) or (self.Op.cmd == 'BNE' and self.Vj != self.Vk):
                self.continuePipeline(int(self.Op.val('Fk')[0]))

            self.Op.mark('READ', self.clock)
            print self.Op.inst + " > RE (" + str(self.clock) + ")"

            if self.Op.cmd in ['BNE', 'BEQ']:
                self.continuePipeline()
                self._setNotBusy()


    def execute(self, bookKeep = False):
        print "Execute: " + str(self.clock)

        if not bookKeep:
            if self.type[:2] in ['In', 'FP']:
                if not self.blocked:
                    self.Vi = self.operate(self.Op.cmd)
                    self.blocked = not self.timer.tick(self.execTime)
                else:
                    self.blocked = not self.timer.tick()
            elif self.type[:2] == 'mA':
                self.blocked = True
                if self.Op.cmd in ['LW', 'L.D']:
                    val = self.memory.read(self.Vj, requestee = self)
                    if val != BUSY:
                        self.Vi = (self.Vi or '') + val
                        if self.Op.cmd == 'LW' or len(self.Vi) == 64:
                            self.Vi = int(self.Vi, 2)
                            self.blocked = False
                        else:
                            self.Vj += 1
                else:
                    val = self.memory.write(self.Vk, self.Vj[:32], requestee = self)
                    if val != BUSY:
                        self.Vj = self.Vj[32:]
                        if len(self.Vj) ==  0:
                            self.blocked = False
                        else:
                            self.Vk += 1
        elif not self.blocked:
            self.Op.mark('EXECUTE', self.clock)
            print self.Op.inst + " > EX (" + str(self.clock) + ")"


    def write(self, bookKeep = False):
        print "Write: " + str(self.clock)
        if not bookKeep:
            if self.Op.cmd not in ['SW', 'S.D']:
                self.regs[self.Op.reg('Fi')]['value'] = self.Vi
        else:
            if self.Op.cmd not in ['SW', 'S.D']:
                self.regs[self.Op.reg('Fi')]['result'] = None
            self.Op.mark('WRITE', self.clock)
            print self.Op.inst + " > WR (" + str(self.clock) + ")"
            self._setNotBusy()

    def tick(self, clock, bookKeep = False):
        self.clock = clock

        if self.busy and self.currentStage < 5:
            if bookKeep and not self.blocked:
                print self.type + '<cycle Ends>',
                self.stages[self.currentStage](bookKeep = True)

            elif not bookKeep:
                if not self.blocked and self.timer.tick():
                    self.currentStage += 1

                if self.currentStage > 1:
                    print self.type + '<cycle start>',
                    self.stages[self.currentStage]()

    def getStage(self):
        return self.currentStage


class Timer:
    def __init__(self):
        self.timer = 0

    def tick(self, timer = None):
        if timer is not None:
            self.timer = timer
        self.timer -= 1
        return self.timer <= 0

class Memory:
    def __init__(self, data = []):
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

    def read(self, loc, requestee = None):
        #Can only serve one per cycle
        if self.servedTime == self.clock:
            return BUSY

        if not self.blocked and (self.requestee is None or (self.requestee == requestee and (self.type != 'R' or self.reqLoc != loc))):
            self.requestee = requestee
            self.type = 'R'
            self.reqLoc = loc
            self.blocked = not self.reqTimer.tick(self.transferTime)

        if self.requestee == requestee:
            print 'Memory Read Access, Current timer: ' + str(self.reqTimer.timer)

        if not self.blocked and self.requestee == requestee:
            self.reqLoc = None
            self.type = None
            self.requestee = None
            self.servedTime = self.clock
            return self._data[loc]

        return BUSY

    def write(self, loc, data, requestee = None):
        #Can only serve one per cycle
        if self.servedTime == self.clock:
            return BUSY

        if not self.blocked and (self.requestee is None or (self.requestee == requestee and (self.type != 'W' or self.reqLoc != loc))):
            self.type = 'W'
            self.reqLoc = loc
            self.requestee = requestee
            self.blocked = not self.reqTimer.tick(self.transferTime)

        if self.requestee == requestee:
            print 'Memory Write Access, Current timer: ' + str(self.reqTimer.timer)

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

    def config(self, noOfBlocks, blockSize, setSize = 1):
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

    def fetchBlock(self, loc, requestee, data = None):
        offset = loc % self.blockSize
        index = (loc / self.blockSize) % self.noOfSets
        tag = loc / (self.blockSize * self.noOfSets)

        cSet = self.localMem[index]

        block = None
        for blk in cSet:
            if blk['tag'] == tag:
                block = blk
                break

        if self.requestee is not None and self.requestee != requestee:
            return BUSY

        #hit
        if block is not None:
            if self.requestee is None:
                self.requestee = requestee
                self.blocked = not self.reqTimer.tick(self.hitTime)

            if requestee == self.requestee and not self.blocked:
                cSet.remove(block)
                cSet.insert(0, block)
                self.requestee = None
                if data is None:
                    return block['words'][offset]
                else:
                    block['words'][offset] = data
                    block['dirty'] = True
                    return True
            else:
                return BUSY

        #miss
        else:
            if self.requestee is None:
                self.requestee = requestee

            self.blocked = not self.reqTimer.tick(1)

            evictBlock = cSet[-1]
            # write if dirty
            if evictBlock['dirty'] and self.missStage['stage'] == 'EVICT' and self.missStage['loc'] < self.blockSize:
                loc = ((tag << int(math.log(self.blockSize, 2) + math.log(self.noOfSets, 2))) |
                        (index << int(math.log(self.blockSize, 2))) | self.missStage['loc'])
                memResult = self.mem.write(loc, evictBlock.words[self.missStage['loc']], requestee = self)
                self.missStage['loc'] += 1 if memResult != BUSY else 0
                if self.missStage['loc'] < self.blockSize:
                    self.mem.lock(self)
                return BUSY
            else:
                if self.missStage['stage'] == 'EVICT':
                    self.missStage['stage'] = {'stage': 'FETCH', 'loc': 0}
                    evictBlock['tag'] = None; evictBlock['dirty'] = False; evictBlock['words'] = [];

                if self.missStage['loc'] < self.blockSize:
                    loc = ((tag << int(math.log(self.blockSize, 2) + math.log(self.noOfSets, 2))) |
                            (index << int(math.log(self.blockSize, 2))) | self.missStage['loc'])
                    memResult = self.mem.read(loc, requestee = self)
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
                    cSet.pop(-1)
                    cSet.insert(0, evictBlock)
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
        return copy.deepcopy(self.fetchBlock(loc, requestee = requestee))

    def write(self, loc, data, requestee):
        print "D-Cache write (Loc: " + str(loc) + "): " + str(data)
        return self.fetchBlock(loc, data = data, requestee = requestee)

#Direct-mapped
class Icache(Cache):
    def __init__(self, mem):
        Cache.__init__(self, mem)
        self.hitTime = 1

    def _getBlockAddress(self, blockAddress):
        return (blockAddress/self.blockSize) % self.noOfBlocks

    def read(self, loc, requestee):
        print "I-Cache read (Loc: " + str(loc) + ")"
        return copy.deepcopy(self.fetchBlock(loc, requestee = requestee))


class Mips:
    InstUnits = {
        'HLT': 'TERM', 'J': 'Branch', 'BEQ': 'Branch', 'BNE': 'Branch',
        'DADD': 'Integer', 'DADDI': 'Integer', 'DSUB': 'Integer', 'DSUBI': 'Integer', 'AND': 'Integer',
        'ANDI': 'Integer', 'OR': 'Integer', 'ORI': 'Integer', 'LI': 'Integer', 'LUI': 'Integer',
        'LW': 'mAccess', 'SW': 'mAccess', 'L.D': 'mAccess', 'S.D': 'mAccess',
        'ADD.D': 'FP adder', 'SUB.D': 'FP adder',
        'MUL.D': 'FP Multiplier',
        'DIV.D': 'FP divider'
    }

    Stages = {
        'FE': 'Fetch',
        'IS': 'Issue',
        'RE': 'Read',
        'EX': 'Execute',
        'WB': 'Write'
    }

    def __init__(self):
        self.scoreBoard = []
        self.termPC = None
        self.registers = {}
        for i in range(0,32):
            self.registers['R' + str(i)] = {'value': 0, 'result': None, 'source': []}
        for i in range(0,32):
            self.registers['F' + str(i)] = {'value': 0.0, 'result': None, 'source': []}

        self._units = {
            'FP adder': [],
            'FP Multiplier': [],
            'FP divider': [],
            'Integer': [],
            'Branch': [],
            'mAccess': []
        }

        self.memory = Memory()
        self._cache = {
            'I-Cache': Icache(self.memory),
            'D-Cache': Dcache(self.memory)
        }

        self._cache['I-Cache'].config(4, 4, 1)
        self._cache['D-Cache'].config(4, 4, 2)

        self._units['Integer'].append(Unit(uType='Integer', regs = self.registers,
                mem = self._cache['D-Cache'], execTime = 1))
        self._units['Branch'].append(Unit(uType='Branch', regs = self.registers,
                execTime = 0, continuePipeline = self._continuePipeline))
        self._units['mAccess'].append(Unit(uType='mAccess', regs = self.registers,
                mem = self._cache['D-Cache'], execTime = 1))

        self.clock = 0
        self.PC = 0
        self.branchPC = None
        self.halt = False
        self.IcacheLookAhead = False
        self._fetchQ = []

#Private
    def _c_inst(self, lines):
        parsedInst = None
        symbolList = {}
        lineNumber = -1
        endAddress = DATA_START - 1
        _inst = self._cache['I-Cache'].getMem()
        for line in lines:
            lineNumber += 1
            line = line.strip()

            if len(line) == 0:
                continue
            symbol = ''
            parsedInst = line.upper().split(":")
            if len(parsedInst) == 2:
                symbol = parsedInst[0].strip()
                symbolList[symbol] = lineNumber
                parsedInst = [parsedInst[1].strip()]
            parsedInst = parsedInst[0].replace('\n', '')
            inst = Inst(parsedInst, symbolList)
            inst.mark('symbol', symbol)
            _inst.append(inst)
            endAddress -= 1

        while endAddress >= 0:
            _inst.append(None)
            endAddress -= 1

    def _c_data(self, lines):
        data = self._cache['D-Cache'].getMem()
        for line in lines:
            data.append(line.replace('\n', ''))

    def _c_config(self, lines):
        iUnit = False
        for line in lines:
            unit = line.replace('\n', '').split(':')
            conf = unit[1][1:].split(",")
            unit = unit[0]

            # Setup Cache
            if unit == 'I-Cache':
                self._cache[unit].config(int(conf[0]), int(conf[1]))
            elif unit == 'D-Cache':
                self._cache[unit].config(int(conf[0]), int(conf[1]), 2)
            # Setup fp Units
            else:
                for i in range(0, int(conf[0])):
                    self._units[unit].append(Unit(uType = unit + str(len(self._units[unit])), regs = self.registers,
                            mem = self._cache['D-Cache'], execTime = int(conf[1])))

    #Execute 1 time tick on all units
    def _tick(self):
        self.clock += 1
        print '\n\n** Clock Cycle ' + str(self._getCurrentTime())

        #Memory tick
        self.memory.tick(self.clock)

        # Cache Tick
        for cache in self._cache:
            self._cache[cache].tick(self.clock)

        #Fetch first, Instruction preference
        cont = self._fetch()
        busy = False

        #Unit tick
        for stage in range(4,-1,-1):
            for unitType, unitList in self._units.iteritems():
                for unit in unitList:
                    if unit.getStage() == stage:
                        busy = busy or unit.Busy()
                        unit.tick(self.clock)

        #All units perform bookkeeping tick
        for stage in range(4,-1,-1):
            for unitType, unitList in self._units.iteritems():
                for unit in unitList:
                    if unit.getStage() == stage:
                        unit.tick(self.clock, bookKeep = True)

        return cont or busy

    def _continuePipeline(self, pc = None):
        if pc is not None:
            self.branchPC = pc
        self.halt = False

    def _getCurrentTime(self):
        return self.clock

    def _fetch(self):
        lookedAhead = False
        if self.IcacheLookAhead:
            print 'Look Ahead',
            lookedAhead = self._cache['I-Cache'].read(self.PC, self)
            if lookedAhead != BUSY:
                self.IcacheLookAhead = False

        inst = self._fetchQ[0] if len(self._fetchQ) > 0 else BUSY

        if inst != BUSY and inst.cmd == 'HLT':
            if self.branchPC is not None:
                self.PC = self.branchPC
                self.branchPC = None
                lookedAhead = False
            if self.termPC is not None and self.termPC != self.PC:
                self._fetchQ.pop(0)
            elif inst != BUSY:
                return False

        if inst != BUSY and inst.cmd != 'HLT':
            units = self._units[Mips.InstUnits[inst.cmd]]
            unit = [unit for unit in units if not unit.Busy()]
            if len(unit) > 0:
                if unit[0].issue(inst, clock = self.clock):
                    self.halt = Mips.InstUnits[inst.cmd] == 'Branch'
                    self._fetchQ.pop(0)

            else:
                inst.mark('STRUCT', 'Y')
        elif inst == BUSY and len(self._fetchQ) > 0:
            self._fetchQ.pop(0)

        if len(self._fetchQ) == 0:
            self._fetchQ.append(self._cache['I-Cache'].read(self.PC, self) if lookedAhead == False else lookedAhead)
            if self._fetchQ[0] != BUSY:
                self._fetchQ[0].mark('FETCH', self._getCurrentTime())
                self._fetchQ[0].mark('STRUCT', 'N')
                self._fetchQ[0].mark('RAW', 'N')
                self._fetchQ[0].mark('WAW', 'N')
                self.PC += 1
                self.IcacheLookAhead = True
                self.scoreBoard.append(self._fetchQ[0])
            if self._fetchQ[0] != BUSY and self._fetchQ[0].cmd == 'HLT':
                self.termPC = self.PC
            if self._fetchQ[0] != BUSY:
                    print 'Fetch (PC: ' + str(self.PC) + ') : ' + self._fetchQ[0].inst

        return True

#Public
    def config(self, fileName):
        lines = []
        #Setup all configurations
        with open(fileName, 'r') as file:
           for line in file:
               lines.append(line)
        getattr(self, "_c_" + fileName[:-4])(lines)

    def setupOutfile(self, fileName):
        self.outFile = fileName
        pass

    def simulate(self):
        while self._tick():
            pass

        #Write out results
        print '\n'
        fmt = '{:<9}'.format
        stages = ['FETCH', 'ISSUE', 'READ', 'EXECUTE', 'WRITE', 'RAW', 'WAW', 'STRUCT']
        with open(self.outFile, 'w') as outfile:

            pLine = ('{:<30}'.format('Instruction') + fmt('FETCH') + fmt('ISSUE') + fmt('READ') + fmt('EXECUTE') + fmt('WRITE') +
                        fmt('RAW') + fmt('WAW') + fmt('STRUCT'))
            print pLine
            outfile.write(pLine + '\n')
            fmt = '{:<8}'.format
            for inst in self.scoreBoard:
                pLine = ('{:>4}'.format(inst.stages['symbol']) + (' ' if inst.stages['symbol'] == '' else ':') +\
                            ' {:<24}'.format(inst.inst))
                outfile.write(pLine + ' ')
                print pLine,
                try:
                    for stage in stages:
                        try:
                            pLine = fmt(inst.stages[stage])
                            outfile.write(pLine + ' ')
                            print pLine,
                        except KeyError as e:
                            pLine = fmt('')
                            outfile.write(pLine + ' ')
                            print pLine,
                            if inst.cmd in ['BNE', 'BEQ', 'J', 'HLT']:
                                continue
                    outfile.write('\n')
                    print ''
                except KeyError as e:
                    print "\nKeyError: {0} ({1})".format(inst.inst, str(e))
                    break
                except AttributeError as e:
                    print "\nAttributeError: {0} ({1})".format(inst, str(e))
                    break
            print '\n'
