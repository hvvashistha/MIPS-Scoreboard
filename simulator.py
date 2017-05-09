#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
from modules.mips import Mips


def initialize():
    configs = ['inst', 'data', 'config']
    processor = Mips()
    for i in range(1, 4):
        processor.config(configs[i - 1], sys.argv[i])
    processor.setupOutfile(sys.argv[4])
    return processor


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print "Usage: python simulator.py inst.txt data.txt config.txt result.txt"
    else:
        proc = initialize()
        proc.simulate()
