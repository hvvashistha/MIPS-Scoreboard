# CMSC 611, Spring 2017, Term project Makefile

run:
	python	./simulator.py inst.txt data.txt config.txt result.txt

clean:
	rm -f ./*.pyc
	rm -f ./modules/*.pyc
	rm -f result.txt