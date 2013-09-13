import os
import sys

#need two as sometimes the python script is run from a different directory
sys.path.append('/'.join(os.getcwd().split('/')[:-2]))
sys.path.append('/'.join(os.getcwd().split('/')[:-3]))

