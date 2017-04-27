import sys

def mb(x): return x * 1024 * 1024
def kb(x): return x * 1024 
def mbit(x): return (x * 1024 * 1024) / 8
def kbit(x): return (x * 1024) / 8
def toMB(x): return x / 1024 / 1024

# convert milliseconds to our base_unit: seconds
def ms(x): return x * 0.001

def bwUnit(bw): 
	kbps = (bw*8/1024)
	return "{bw:.0f}kbps".format(bw=kbps) if kbps < 1024 else "{bw:.3f}Mbps".format(bw=kbps/1024)

progressFH = sys.stderr
