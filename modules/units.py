#!/usr/bin/env python
# -*- coding: utf-8 -*-
from modules import Timer, BUSY


# Registers {value, producer, consumer}
class Unit:
    def __init__(self, uType, regs, mem=None, execTime=1,
                 continuePipeline=None):
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
    def issue(self, inst=None, bookKeep=False, clock=None):
        if inst is None:
            print "Issue: " + str(self.clock)

        if clock is not None:
            self.clock = clock

        if bookKeep:
            self.Op.mark('ISSUE', self.clock)
            print self.Op.inst + " > IS (" + str(self.clock) + ")"
            if self.Op.cmd == 'J':
                self.continuePipeline(int(self.Op.Fi))
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
                self.regs[Fi]['result'] = {
                    'type': self.type,
                    'clock': self.clock
                }

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

    def read(self, bookKeep=False):
        print "Read: " + str(self.clock)

        i = 'Fi'
        j = 'Fj'
        k = 'Fk'

        if self.Op.cmd in ['SW', 'S.D', 'BEQ', 'BNE']:
            k = j
            j = i

        Fj = self.Op.reg(j)
        Fk = self.Op.reg(k)

        if not bookKeep:
            val = None
            self.blocked = False
            if self.Vj is None or self.Vj == BUSY:
                if Fj is None:
                    self.Vj, mem = self.Op.val(j)
                elif (self.regs[Fj]['result'] is None or
                      self.regs[Fj]['result']['type'] == self.type or
                      self.regs[Fj]['result']['clock'] == self.clock):

                    val = self.regs[Fj]['value']
                    self.Vj, mem = self.Op.val(j, val)
                else:
                    self.Op.mark('RAW', 'Y')
                    self.blocked = True

            if self.Vk is None or self.Vk == BUSY:
                if Fk is None:
                    self.Vk, mem = self.Op.val(k)
                elif (self.regs[Fk]['result'] is None or
                      self.regs[Fk]['result']['type'] == self.type or
                      self.regs[Fk]['result']['clock'] == self.clock):
                    val = self.regs[Fk]['value']
                    self.Vk, mem = self.Op.val(k, val)
                else:
                    self.Op.mark('RAW', 'Y')
                    self.blocked = True

        elif not self.blocked:
            if Fj is not None:
                self.regs[Fj]['source'].remove(self.type)
            if Fk is not None:
                self.regs[Fk]['source'].remove(self.type)

            if((self.Op.cmd == 'BEQ' and self.Vj == self.Vk) or
               (self.Op.cmd == 'BNE' and self.Vj != self.Vk)):
                    self.continuePipeline(int(self.Op.val('Fk')[0]))

            self.Op.mark('READ', self.clock)
            print self.Op.inst + " > RE (" + str(self.clock) + ")"

            if self.Op.cmd in ['BNE', 'BEQ']:
                self.continuePipeline()
                self._setNotBusy()

    def execute(self, bookKeep=False):
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
                    val = self.memory.read(self.Vj, requestee=self)
                    if val != BUSY:
                        self.Vi = (self.Vi or '') + val
                        if self.Op.cmd == 'LW' or len(self.Vi) == 64:
                            self.Vi = int(self.Vi, 2)
                            self.blocked = False
                        else:
                            self.Vj += 1
                else:
                    val = self.memory.write(self.Vk, self.Vj[:32],
                                            requestee=self)
                    if val != BUSY:
                        self.Vj = self.Vj[32:]
                        if len(self.Vj) == 0:
                            self.blocked = False
                        else:
                            self.Vk += 1
        elif not self.blocked:
            self.Op.mark('EXECUTE', self.clock)
            print self.Op.inst + " > EX (" + str(self.clock) + ")"

    def write(self, bookKeep=False):
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

    def tick(self, clock, bookKeep=False):
        self.clock = clock

        if self.busy and self.currentStage < 5:
            if bookKeep and not self.blocked:
                print self.type + '<cycle Ends>',
                self.stages[self.currentStage](bookKeep=True)

            elif not bookKeep:
                if not self.blocked and self.timer.tick():
                    self.currentStage += 1

                if self.currentStage > 1:
                    print self.type + '<cycle start>',
                    self.stages[self.currentStage]()

    def getStage(self):
        return self.currentStage
