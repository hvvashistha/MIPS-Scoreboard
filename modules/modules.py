#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re


# Status Codes
BUSY = 'BUSY'
BANDWIDTH = 64
DATA_START = 64


class Timer:
    def __init__(self):
        self.timer = 0

    def tick(self, timer=None):
        if timer is not None:
            self.timer = timer
        self.timer -= 1
        return self.timer <= 0


class Inst:
    registers = ['Fi', 'Fj', 'Fk']

    def __init__(self, instruction, symbolList):
        self.inst = instruction
        instruction = instruction.replace(",", "")
        instruction = re.split('\s+', instruction)
        self.cmd = instruction[0]
        self.stages = {}

        if self.cmd in ['BNE', 'BEQ', 'J'] and not instruction[-1].isdigit():
            instruction[-1] = str(symbolList[instruction[-1]])

        if self.cmd != 'HLT':
            for i in range(1, len(instruction)):
                setattr(self, Inst.registers[i - 1], instruction[i])

    def mark(self, stage, value):
        if stage in ['WAW', 'RAW'] and value == 'Y':
            print 'Marking ' + self.inst + ' : ' + stage + ' ' + value
        if not hasattr(self.stages, stage):
            self.stages[stage] = value

    def val(self, reg, regValue=None):
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
                    val = val / 4       # Word Align
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
