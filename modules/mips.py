#!/usr/bin/env python
# -*- coding: utf-8 -*-
from modules import *
from memory import Memory
from cache import Icache, Dcache
from units import Unit


class Mips:
    InstUnits = {
        'HLT': 'TERM', 'J': 'Branch', 'BEQ': 'Branch', 'BNE': 'Branch',

        'DADD': 'Integer', 'DADDI': 'Integer', 'DSUB': 'Integer',
        'DSUBI': 'Integer', 'AND': 'Integer', 'ANDI': 'Integer',
        'OR': 'Integer', 'ORI': 'Integer', 'LI': 'Integer', 'LUI': 'Integer',

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

        for i in range(0, 32):
            self.registers['R' + str(i)] = {
                'value': 0,
                'result': None,
                'source': []
            }

        for i in range(0, 32):
            self.registers['F' + str(i)] = {
                'value': 0.0,
                'result': None,
                'source': []
            }

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

        self._units['Integer'].append(
            Unit(uType='Integer', regs=self.registers,
                 mem=self._cache['D-Cache'], execTime=1))

        self._units['Branch'].append(
            Unit(uType='Branch', regs=self.registers, execTime=0,
                 continuePipeline=self._continuePipeline))
        self._units['mAccess'].append(
            Unit(uType='mAccess', regs=self.registers,
                 mem=self._cache['D-Cache'], execTime=1))

        self.clock = 0
        self.PC = 0
        self.branchPC = None
        self.halt = False
        self.IcacheLookAhead = False
        self.instructionHit = 0
        self._fetchQ = []

# Private
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
                    self._units[unit].append(
                        Unit(uType=unit + str(len(self._units[unit])),
                             regs=self.registers, mem=self._cache['D-Cache'],
                             execTime=int(conf[1])))

    # Execute 1 time tick on all units
    def _tick(self):
        self.clock += 1
        print '\n\n** Clock Cycle ' + str(self._getCurrentTime())

        # Memory tick
        self.memory.tick(self.clock)

        # Cache Tick
        for cache in self._cache:
            self._cache[cache].tick(self.clock)

        # Fetch first, Instruction preference
        cont = self._fetch()
        busy = False

        # Unit tick
        for stage in range(4, -1, -1):
            for unitType, unitList in self._units.iteritems():
                for unit in unitList:
                    if unit.getStage() == stage:
                        busy = busy or unit.Busy()
                        unit.tick(self.clock)

        # All units perform bookkeeping tick
        for stage in range(4, -1, -1):
            for unitType, unitList in self._units.iteritems():
                for unit in unitList:
                    if unit.getStage() == stage:
                        unit.tick(self.clock, bookKeep=True)

        return cont or busy

    def _continuePipeline(self, pc=None):
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
                self.instructionHit += 1
                self.IcacheLookAhead = False

        inst = self._fetchQ[0] if len(self._fetchQ) > 0 else BUSY

        if inst != BUSY and inst.cmd == 'HLT' and self.branchPC is None:
            if self.termPC is not None and self.termPC != self.PC:
                self._fetchQ.pop(0)
            elif inst != BUSY:
                return False

        if inst != BUSY and inst.cmd != 'HLT' and self.branchPC is None:
            units = self._units[Mips.InstUnits[inst.cmd]]
            unit = [unit for unit in units if not unit.Busy()]
            if len(unit) > 0 and not self.halt:
                if unit[0].issue(inst, clock=self.clock):
                    self.halt = Mips.InstUnits[inst.cmd] == 'Branch'
                    self._fetchQ.pop(0)
            else:
                inst.mark('STRUCT', 'Y')
        elif inst == BUSY and len(self._fetchQ) > 0:
            self._fetchQ.pop(0)

        if len(self._fetchQ) == 0:

            self._fetchQ.append(
                self._cache['I-Cache'].read(self.PC, self)
                if lookedAhead is False else lookedAhead)

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
                print('Fetch (PC: ' + str(self.PC) + ') : ' +
                      self._fetchQ[0].inst)

                if self.branchPC is not None:
                    if len(self._fetchQ) > 0:
                        self._fetchQ.pop(0)
                    self._fetchQ.append(BUSY)
                    self.PC = self.branchPC
                    self.branchPC = None

        return True

# Public
    def config(self, conf, fileName):
        lines = []
        # Setup all configurations
        with open(fileName, 'r') as file:
            for line in file:
                lines.append(line)
        getattr(self, "_c_" + conf)(lines)

    def setupOutfile(self, fileName):
        self.outFile = fileName
        pass

    def simulate(self):
        while self._tick():
            pass

        # Write out results
        print '\n'
        fmt = '{:<9}'.format
        stages = ['FETCH', 'ISSUE', 'READ', 'EXECUTE', 'WRITE', 'RAW', 'WAW',
                  'STRUCT']

        with open(self.outFile, 'w') as outfile:

            pLine = ('{:<30}'.format('Instruction') + fmt('FETCH') +
                     fmt('ISSUE') + fmt('READ') + fmt('EXECUTE') +
                     fmt('WRITE') + fmt('RAW') + fmt('WAW') + fmt('STRUCT'))

            print pLine
            outfile.write(pLine + '\n')
            fmt = '{:<8}'.format
            for inst in self.scoreBoard:
                pLine = ('{:>4}'.format(inst.stages['symbol']) +
                         (' ' if inst.stages['symbol'] == '' else ':') +
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

            cacheReq = self.instructionHit

            pLine = ('Total number of access requests for instruction cache:' +
                     ' ' + str(cacheReq))
            outfile.write(pLine + '\n')
            print pLine

            pLine = ('Number of instruction cache hits: ' +
                     str(cacheReq - self._cache['I-Cache'].noOfMiss))
            outfile.write(pLine + '\n')
            print pLine

            cacheReq = (self._cache['D-Cache'].noOfHits +
                        self._cache['D-Cache'].noOfMiss)

            pLine = ('Total number of access requests for data cache: ' +
                     str(cacheReq))
            outfile.write(pLine + '\n')
            print pLine

            pLine = ('Number of data cache hits: ' +
                     str(self._cache['D-Cache'].noOfHits))
            outfile.write(pLine + '\n')
            print pLine
