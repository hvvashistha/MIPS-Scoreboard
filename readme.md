## MIPS Scoreboard Simulation

This project is part of Advanced Computer Architecture course [CMSC 611](https://www.csee.umbc.edu/~younis/CMSC611/CMSC611.htm) at UMBC.

[MIPS architecture](https://en.wikipedia.org/wiki/MIPS_architecture) is RISC architecutre developed by MIPS technologies.
[Scoreboarding](https://en.wikipedia.org/wiki/Scoreboarding) is one of the strategy for dynamic processor pipeline queuing. It was developed for MIPS architecture and was employed in CDC 6600 computers/

### Intructions for make file

To clean the directory:
```
make clean
```

To run the simulation:
```
make run
```

To run with your own configuration and data files:
```
python  ./simulator.py <inst.txt> <data.txt> <config.txt> <result.txt>
```
