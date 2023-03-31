# Based on: Arbitrary waveform generator functions
# Achieves 125Msps when running 125MHz clock
# Rolf Oldeman, 13/2/2021. CC BY-NC-SA 4.0 licence

# modified by wolfi for 10bit DAC and integration in micro-gui
# version 2-Oct-2021
# version 3-Nov-2021 enabled duplication and changed to 8-bit DAC
#                                                       ---------

from machine import Pin, mem32, freq
from rp2 import PIO, StateMachine, asm_pio
from array import array
from math import pi, sin, exp, sqrt, floor
from uctypes import addressof
from random import random
import struct
import gc
import sys
import utime
from ui import maxsamp


#define AWG base constants
DACbits=8 #Number of nits in the DAC / R2R Ladder Network
maxDACvalue=(2**DACbits)-1
fclock=freq() #clock frequency of the pico

#print('0 wavegen: fclock= ', str(fclock/1000000), ' MHz')

# use DMA channels 2 and 3 as ch0 and ch1 are used by preriferals such as SPI for the display
DMA_BASE=0x50000000

CH2_READ_ADDR  =DMA_BASE+0x080
CH2_WRITE_ADDR =DMA_BASE+0x084
CH2_TRANS_COUNT=DMA_BASE+0x088
CH2_CTRL_TRIG  =DMA_BASE+0x08c
CH2_AL1_CTRL   =DMA_BASE+0x090

CH3_READ_ADDR  =DMA_BASE+0x0c0
CH3_WRITE_ADDR =DMA_BASE+0x0c4
CH3_TRANS_COUNT=DMA_BASE+0x0c8
CH3_CTRL_TRIG  =DMA_BASE+0x0cc
CH3_AL1_CTRL   =DMA_BASE+0x0d0

PIO0_BASE      =0x50200000
PIO0_TXF0      =PIO0_BASE+0x10
PIO0_SM0_CLKDIV=PIO0_BASE+0xc8


#state machine that just pushes bytes to the 10 pins
@asm_pio(out_init=(PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,
                   PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH,PIO.OUT_HIGH),
         out_shiftdir=PIO.SHIFT_RIGHT, autopull=True, pull_thresh=32)
def stream():
    out(pins,8) # push 8 bits at a time.

sm = StateMachine(0, stream, freq=fclock, out_base=Pin(0))
sm.active(1)

# set pins 0 and 1 to low to reduce digital noise
#Pin(0, Pin.OUT, value=0)
#Pin(1, Pin.OUT, value=0)

#2-channel chained DMA. channel 0 does the transfer, channel 1 reconfigures
p=array('I',[0]) #global 1-element array
def startDMA(ar,nword):
    #first disable the DMAs to prevent corruption while writing
    mem32[CH3_AL1_CTRL]=0
    mem32[CH2_AL1_CTRL]=0
    #setup first DMA which does the actual transfer
    mem32[CH2_READ_ADDR]=addressof(ar)
    mem32[CH2_WRITE_ADDR]=PIO0_TXF0
    mem32[CH2_TRANS_COUNT]=nword
    IRQ_QUIET=0x1 #do not generate an interrupt
    TREQ_SEL=0x00 #wait for PIO0_TX0
    CHAIN_TO=3    #start channel 1 when done
    RING_SEL=0
    RING_SIZE=0   #no wrapping
    INCR_WRITE=0  #for write to array
    INCR_READ=1   #for read from array
    DATA_SIZE=2   #32-bit word transfer
    HIGH_PRIORITY=1
    EN=1
    CTRL0=(IRQ_QUIET<<21)|(TREQ_SEL<<15)|(CHAIN_TO<<11)|(RING_SEL<<10)|(RING_SIZE<<9)|(INCR_WRITE<<5)|(INCR_READ<<4)|(DATA_SIZE<<2)|(HIGH_PRIORITY<<1)|(EN<<0)
    mem32[CH2_AL1_CTRL]=CTRL0
    #setup second DMA which reconfigures the first channel
    p[0]=addressof(ar)
    mem32[CH3_READ_ADDR]=addressof(p)
    mem32[CH3_WRITE_ADDR]=CH2_READ_ADDR
    mem32[CH3_TRANS_COUNT]=1
    IRQ_QUIET=0x1 #do not generate an interrupt
    TREQ_SEL=0x3f #no pacing
    CHAIN_TO=2    #start channel 0 when done
    RING_SEL=0
    RING_SIZE=0   #no wrapping
    INCR_WRITE=0  #single write
    INCR_READ=0   #single read
    DATA_SIZE=2   #32-bit word transfer
    HIGH_PRIORITY=1
    EN=1
    CTRL1=(IRQ_QUIET<<21)|(TREQ_SEL<<15)|(CHAIN_TO<<11)|(RING_SEL<<10)|(RING_SIZE<<9)|(INCR_WRITE<<5)|(INCR_READ<<4)|(DATA_SIZE<<2)|(HIGH_PRIORITY<<1)|(EN<<0)
    mem32[CH3_CTRL_TRIG]=CTRL1


def stopDMA():
    #disable the DMAs to prevent corruption while writing
    mem32[CH2_AL1_CTRL]=0
    mem32[CH3_AL1_CTRL]=0



def setupwave(buf,w):

    w['AWG_status'] = 'calc wave'
    f=w['frequency']
    maxnsamp = maxsamp

    div=fclock/(f*maxnsamp) # required clock division for maximum buffer size
    if div<1.0:  #can't speed up clock, duplicate wave instead
        dup=int(1.0/div)
        nsamp=int((maxnsamp*div*dup+0.5)/4)*4 #force multiple of 4
        clkdiv=1
        
    else:        #stick with integer clock division only
        clkdiv=int(div)+1
        nsamp=int((maxnsamp*div/clkdiv+0.5)/4)*4 #force multiple of 4
        dup=1
    #print('1 fill the buffer: f= ', f, 'maxnsamp= ', maxnsamp, 'nsamp= ', nsamp, 'dup= ', dup)
    #print('nsamp= ', nsamp, 'dup= ', dup)



    try:
        for isamp in range(nsamp):
            buf[isamp] = max(0,min(maxDACvalue,int((2**DACbits)*eval(w,dup*(isamp+0.5)/nsamp))))
            #print('1: ', isamp, ' ', value)

        w['nsamp'] = nsamp
     
        #set the clock divider
        clkdiv_int=min(clkdiv,65535)
        clkdiv_frac=0 #fractional clock division results in jitter
        mem32[PIO0_SM0_CLKDIV]=(clkdiv_int<<16)|(clkdiv_frac<<8)

        F_actual = fclock/clkdiv_int/nsamp*dup
        w['F_out'] = F_actual
        #print('F_AWS= ', f, '  F_actual= ', F_actual, '  F-err= ', w['F_error'])

        gc.collect()

        startDMA(buf,int(nsamp/4)) #we transfer 4 bytes at a time, so samples / 4

        w['AWG_status']='running'

    except Exception as e:
        print('setupwave crashed: ', e)
        raise

#evaluate the content of a wave
def eval(w,x):
    x=x*w['replicate']
    x=x-floor(x)  #reduce x to 0.0-1.0 range
    v=w['func'](x,w['pars'])
    v=v*w['amplitude']
    v=v+w['offset']
    return v

# define waveforms
def sine(x,pars):
    return sin(x*2*pi)

def pulse(x,pars): #risetime,uptime,falltime
    if x<pars[0]: return x/pars[0]
    if x<pars[0]+pars[1]: return 1.0
    if x<pars[0]+pars[1]+pars[2]: return 1.0-(x-pars[0]-pars[1])/pars[2]
    return 0.0

def gaussian(x,pars):
    return exp(-((x-0.5)/pars[0])**2)

def sinc(x,pars):
    if x==0.5: return 1.0
    else: return sin((x-0.5)/pars[0])/((x-0.5)/pars[0])

def exponential(x,pars):
    return exp(-x/pars[0])

def noise(x,pars): #pars[0]=quality: 1=uniform >10=gaussian
    return sum([random()-0.5 for _ in range(pars[0])])*sqrt(12/pars[0])

# eof