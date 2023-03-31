# Arbitray waveform generator (AWG)
#
# 
# updated by wolfi:
version_date = '18-Feb-2022'
# 
# This version is modified for 8-bit DAC 
# --------------------------------------
#
# RP2040 based arbitrary wave form generator (AWG)
#
# GUI based on micro-gui released under the MIT License (MIT). See LICENSE.
# Copyright (c) 2021 Peter Hinch
#
# AWG based on "Arbitrary waveform generator for Rasberry Pi Pico"
# Rolf Oldeman, 13/2/2021. CC BY-NC-SA 4.0 licence
# modified for 10bit R2R ladder network DAC

# hardware_setup must be imported before other modules because of RAM use.
# To reduce memory fragmentation, next buffers for AWG are created
# then AWG functions are imported, last all gui functions are imported

#v3-Nov: modified for 8-bit DAC
#v10-Nov: implemented micro-gui "adjusters" for parameters
#v21-Nov: implemented controls for display update to reduce noise while generator is running
#v18-Feb: initialize parameters only if function has changes, otherwise keep values
#         bracket parameters for gaussian, sinc and exponential, so they always create a "good" output wave

import hardware_setup  # Create a display instance
import gc

gc.collect() # precaution to free up unused RAM

#make buffers for the waveform.
#large buffers give better results but are slower to fill
wavbuf={}

maxsamp= 512   #must be a multiple of 4. Will be changed dynamically in wave_gen based on frequency
wavbuf[0]=bytearray(maxsamp)

#AWG_status flag
# status:   Meaning:
# -------   --------
# stopped     generator output stopped, new set up trigger is allowed, initialization status
# calc wave   generetor set up is trigger, wave form is calculated, no further trigger is allowed
# running     calculation finished, generator output active, new set up trigger is allowed
# -- init --  intitialization, generator not yet started using start button

#import AWG functions
from wave_gen import *
#define wave with defaults
wave = {'func' : sine,
        'frequency' : 2000,
        'amplitude' : 0.48,
        'offset' : 0.5,
        'phase' : 0,
        'replicate' : 1,
        'pars' : [0.2, 0.4, 0.2],
        'frequency_value' : 2000,
        'freq_range' : 1,
        'AWG_status' : '- init -',
        'nsamp' : 0,
        'F_out' : 0,}

# defaults for the different functions for initialization, when function is selected
# values only if max_value needs to be defined to ensure proper wave form
max_ampl = {'sine' : 0.48,
            'pulse' : 0.89,
            'gauss' : 0.55,
            'sinc' : 0.5,
            'expo' : 0.5,
            'noise' : 1,
            }



gc.collect() # precaution to free up unused RAM

# import gui functions
from gui.core.ugui import Screen, ssd

from gui.widgets.label import Label
from gui.widgets.buttons import ButtonList
from gui.widgets.dropdown import Dropdown
from gui.widgets.sliders import HorizSlider
from gui.widgets.scale_log import ScaleLog
from gui.core.writer import CWriter
from gui.widgets.adjuster import Adjuster

# set font for CWriter
import gui.fonts.font6 as font      # FreeSans 14 pix


from gui.core.colors import *
import sys
from machine import Pin, freq
import utime
import uasyncio as asyncio
from gui.primitives.delay_ms import Delay_ms

# set GP23 to high to switch Pico power supply from PFM to PWM to reduce noise
GP23 = Pin(23, Pin.OUT)
GP23.value(1)

gc.collect()    # precaution to free up unused RAM


#======= define UI base screen =======

head_line = 'Arbirtaty 8-bit wave form generator v'
version = version_date


class BaseScreen(Screen):

    def __init__(self):


        startstop_buttons = []

        table_startstop_buttons = (
            {'text' : 'setup generator', 'args' : ('setup',), 'bgcolor' : LIGHTGREEN,
                    'bdcolor' : False, 'litcolor' : GREEN},
            {'text' : 'stop   generator', 'args' : ('stop',), 'bgcolor' : LIGHTRED,
                    'bdcolor' : False, 'litcolor' : RED},
        )

        # function to disable = "grey-out" all controls except "stop" while generator is running
        def grey_out_all():
            # disable all parameters
            rise_adj.greyed_out(val=1)
            up_adj.greyed_out(val=1)
            fall_adj.greyed_out(val=1)
            width_adj.greyed_out(val=1)
            noise_adj.greyed_out(val=1)
            expo_adj.greyed_out(val=1)
            #
            func_menu.greyed_out(val=1)
            freq_menu.greyed_out(val=1)
            frange_menu.greyed_out(val=1)
            Amplitude.greyed_out(val=1)
            Offset.greyed_out(val=1)


        def enable_controls():
            func_menu.greyed_out(val=0)
            freq_menu.greyed_out(val=0)
            frange_menu.greyed_out(val=0)
            Amplitude.greyed_out(val=0)
            Offset.greyed_out(val=0)
            #enable parameter controls based on last function selected
            function_cb(func_menu)

        # function to refresh screen then stop refresh
        async def refresh_and_stop():
            
             BaseScreen.rfsh_start.set()        # One more refresh
             BaseScreen.rfsh_done.clear()
             await BaseScreen.rfsh_done.wait()  # Wait for a refresh to end
             await asyncio.sleep_ms(200)        # Allow time to finish display update
             BaseScreen.rfsh_start.clear()      # Stop refreshing



        # definition of call backs
        def startstop_cb(button, val):
            gc.collect()
            #print('0: mem at startstop callback', gc.mem_free())


            if val == 'setup':

                grey_out_all()

                wave['AWG_status']='calc wave'
                update_status(wave['AWG_status'])
                wave['frequency'] = wave['frequency_value'] * wave['freq_range']

                #input('press ENTER for setup wave')

                setupwave(wavbuf[0],wave)

                update_status(wave['AWG_status'])
                nsamp_lbl.value(str(wave['nsamp']))
                
                # due to digital wave synthesis, AWG frequency can deviate from requested frequency
                # actual frequency is calculated by AWG and displayed to the user
                f_out = wave['F_out']
                if f_out > 999999:
                    fout_lbl.value('{:7.3f}'.format(f_out/1000000) + ' MHz')
                elif f_out > 999:
                    fout_lbl.value('{:7.3f}'.format(f_out/1000) + ' kHz')
                else:
                    fout_lbl.value('{:7.3f}'.format(f_out) + ' Hz')


                # refresh screen and stop
                asyncio.create_task(refresh_and_stop())
                refresh_and_stop()


            elif val == 'stop':
                wave['AWG_status']='stopped'
                update_status(wave['AWG_status'])
                wave['nsamp'] = 0
                nsamp_lbl.value(str(wave['nsamp']))
                fout_lbl.value('0' + ' Hz')
                stopDMA()

                BaseScreen.rfsh_start.set()
                enable_controls()

            else:
                print('wrong button received')



        def function_cb(dd):
            fun = dd.textvalue()
            # enable/disable parameter controls as required by function
            if fun == 'sine':
                rise_adj.greyed_out(val=1)
                up_adj.greyed_out(val=1)
                fall_adj.greyed_out(val=1)
                width_adj.greyed_out(val=1)
                noise_adj.greyed_out(val=1)
                expo_adj.greyed_out(val=1)
                wave['replicate'] = 1
                if wave['func'] != sine: # initialize wave for sine
                    wave['func'] = sine
                    Amplitude.value(max_ampl['sine'])
                    Offset.value(0.5)

            elif fun == 'pulse':
                width_adj.greyed_out(val=1)
                rise_adj.greyed_out(val=0)
                up_adj.greyed_out(val=0)
                fall_adj.greyed_out(val=0)
                noise_adj.greyed_out(val=1)
                expo_adj.greyed_out(val=1)
                wave['replicate'] = 1
                if wave['func'] != pulse: # initialize wave for pulse
                    rise_adj.value(0) # reset parameter as it is used by other functions
                    wave['func'] = pulse
                    Amplitude.value(max_ampl['pulse'])
                    Offset.value(0)
                    rise_adj.value(0.05)
                    up_adj.value(0.5)
                    fall_adj.value(0.05)


            elif fun == 'gauss':
                width_adj.greyed_out(val=0)
                rise_adj.greyed_out(val=1)
                up_adj.greyed_out(val=1)
                fall_adj.greyed_out(val=1)
                noise_adj.greyed_out(val=1)
                expo_adj.greyed_out(val=1)
                wave['replicate'] = 1
                if wave['func'] != gaussian: # initialize wave for gaussian
                    wave['func'] = gaussian
                    Amplitude.value(max_ampl['gauss'])
                    Offset.value(0)
                    width_adj.value(0.3)


            elif fun == 'noise':
                width_adj.greyed_out(val=1)
                rise_adj.greyed_out(val=1)
                up_adj.greyed_out(val=1)
                fall_adj.greyed_out(val=1)
                noise_adj.greyed_out(val=0)
                expo_adj.greyed_out(val=1)
                wave['replicate'] = 1
                if wave['func'] != noise: # initialize wave for noise
                    wave['func'] = noise
                    Amplitude.value(max_ampl['noise'])
                    Offset.value(0)
                    noise_adj.value(0.45)

            elif fun == 'sinc':
                width_adj.greyed_out(val=0)
                rise_adj.greyed_out(val=1)
                up_adj.greyed_out(val=1)
                fall_adj.greyed_out(val=1)
                noise_adj.greyed_out(val=1)
                expo_adj.greyed_out(val=1)
                wave['replicate'] = 1
                if wave['func'] != sinc: # initialize wave for sinc
                    wave['func'] = sinc
                    Amplitude.value(max_ampl['sinc'])
                    Offset.value(0.5)
                    width_adj.value(0.4)

            elif fun == 'expo':
                width_adj.greyed_out(val=0)
                rise_adj.greyed_out(val=1)
                up_adj.greyed_out(val=1)
                fall_adj.greyed_out(val=1)
                noise_adj.greyed_out(val=1)
                expo_adj.greyed_out(val=0)
                wave['replicate'] = -1
                if wave['func'] != exponential: # initialize wave for exponential
                    wave['func'] = exponential
                    Amplitude.value(max_ampl['expo'])
                    Offset.value(0)
                    width_adj.value(0.5)
                    expo_adj.value(0.49)

            else:
                print('no valid function selected')



        def amplitude_cb(s):
            v = s.value()
            wave['amplitude'] = v

        def offset_cb(s):
            v = s.value()
            wave['offset'] = v

        def freqlog_cb(f):
            v = f.value()
            if v < 80:
                freq_lbl.value('{:3.1f}'.format(2*v))    
            else:
                freq_lbl.value('{:4.0f}'.format(2*v))
            wave['frequency_value'] = int(2*v)

        def freq_range_cb(dd):
            f = dd.textvalue()
            if f == 'Hz':
                wave['freq_range'] = 1
            if f == 'kHz':
                wave['freq_range'] = 1000

        def rise_cb(s):
            v = s.value()
            rise_lbl.value('{:0.3f}'.format(v))
            wave['pars'][0] = v

        def up_cb(s):
            v = s.value()
            up_lbl.value('{:0.3f}'.format(v))
            wave['pars'][1] = v

        def fall_cb(s):
            v = s.value()
            fall_lbl.value('{:0.3f}'.format(v))
            wave['pars'][2] = v

        def width_cb(s):
            # different default values for gaussian, sinc and exponential
            # map adjuster range 0...1 to meaningful parameter ranges 
            # this "brackets" ranges for gaussian, sinc and exponential
            v = s.value()
            if wave['func'] == gaussian:
                width_lbl.value('{:0.3f}'.format(v*0.3+0.005))
                wave['pars'][0] = v*0.3+0.05
            elif wave['func'] == sinc:
                width_lbl.value('{:0.3f}'.format(v*0.06+0.005))
                wave['pars'][0] = v*0.08+0.005
            elif wave['func'] == exponential:
                width_lbl.value('{:0.3f}'.format(v*0.15+0.005))
                wave['pars'][0] = v*0.15+0.005
            else: # for first initialization set to zero
                width_lbl.value('{:0.3f}'.format(0.0))
                wave['pars'][0] = 0.0    

        def expo_cb(s):
            v = s.value()
            if v < 0.5:
                repli = -1
            else:
                repli = 1
            #print('v= ', v, 'repli= ', repli)
            expo_lbl.value('{:1.0f}'.format(repli))
            wave['replicate'] = repli

        def noise_cb(s):
            v = s.value()
            noise_lbl.value('{:1.0f}'.format(int(v*8)))
            wave['pars'][0] = int(v*8)

        def update_status(s):
            if s == 'stopped':
                status_lbl.value(text = s, bdcolor = None, bgcolor = LIGHTRED, fgcolor = WHITE)
            elif s == 'calc wave':
                status_lbl.value(text = s, bdcolor = None, bgcolor = BLACK, fgcolor = ORANGE)
            elif s == 'running':
                status_lbl.value(text = s, bdcolor = None, bgcolor = LIGHTGREEN, fgcolor = WHITE)
            elif s == '- init -':
                status_lbl.value(text = s, bdcolor = None, bgcolor = DARKBLUE, fgcolor = ORANGE)
            else:
                status_lbl.value(text = 'no stat' , bdcolor = RED, bgcolor = WHITE, fgcolor = RED)

        # change the frequency legend; two versions: legendm_cb changes legends to k(Hz) and M(Hz)
        #   based on frequency range field
        # whereas legend_cb does only k(Hz) in the scale, as frequency range is a separate field
        #   MHZ will show as "1000 khz"
        def legendm_cb(f):
            if wave['freq_range'] == 1:
                if f < 999:
                    return '{:<1.0f}'.format(f)
                return '{:<1.0f}K'.format(f/1000)
            if wave['freq_range'] == 1000:
                if f < 999:
                    return '{:<1.0f}K'.format(f)
                return '{:<1.0f}M'.format(f/1000)

        def legend_cb(f):
            if f < 1999:
                return '{:<1.0f}'.format(2*f)
            return '{:<1.0f}K'.format(2*f/1000)
            
        # ======== instantiate screen and writer =======
        super().__init__()
        wri = CWriter(ssd, font, GREEN, BLACK, verbose=False)

        # headline and version
        col = 2
        row = 2
        Label(wri, row, col, head_line + version, fgcolor = BLUE, bgcolor = LIGHTGREY)
        

        # create function labels
        row = 25
        Label(wri, row, col, 'Function:')
        row -=2
        Label(wri, row, col+212, 'AWG:', fgcolor = BLUE)

        status_lbl=Label(wri, row, col+260, 65, bgcolor = ORANGE, fgcolor = BLACK)
        update_status(wave['AWG_status'])

        row += 45
        Label(wri, row, col, 'Frequency:', fgcolor = CYAN)
        row += 45
        Label(wri, row, col, 'Amplitude:', fgcolor = LIGHTGREY)
        col += 170
        Label(wri, row, col, 'Offset:', fgcolor = LIGHTGREY)

        row = 40
        col = 216
        Label(wri, row, col, 'samples:', fgcolor = BLUE)
        nsamp_lbl = Label(wri, row, col+55, '000', bgcolor = BLUE, fgcolor = WHITE)

        # ======= create AWG controls =======

        # dropdown for function
        col = 80
        row = 22
        func_menu = Dropdown(wri, row, col, callback=function_cb,
                elements = ('sine', 'pulse', 'gauss', 'sinc', 'expo', 'noise'),
                bdcolor = GREEN, bgcolor = DARKGREEN)

        
        # FREQUENCY: Scale and range label
        # Instantiate Label first, because Scale callback will run now.

        row +=35
        freq_lbl = Label(wri, row+11, col+120, 50, bdcolor=CYAN, fgcolor=YELLOW)

        freq_menu = ScaleLog(wri, row-5, col, width = 110, legendcb = legend_cb,
                pointercolor=RED, fontcolor=YELLOW, bdcolor=CYAN,
                callback=freqlog_cb, value=1000, decades = 4, active=True)

        frange_menu = Dropdown(wri, row+10, col+180, callback=freq_range_cb, elements = ('Hz', 'kHz'),
                bdcolor = CYAN, fgcolor = YELLOW, bgcolor = DARKGREEN)

        # Amplitude and offset sliders
        row +=60
        Amplitude = HorizSlider(wri, row, col, callback=amplitude_cb,
               divisions = 10, width = 70, height = 12, fgcolor = LIGHTGREY, bdcolor=ORANGE,
                slotcolor=BLUE, legends=('0', '0.5', '1'), value=0.5, active=True)

        Offset = HorizSlider(wri, row, col+150, callback=offset_cb,
               divisions = 10, width = 70, height = 12, fgcolor = LIGHTGREY, bdcolor=ORANGE,
                slotcolor=BLUE, legends=('0', '0.5', '1'), value=0.5, active=True)

        # Define controls for pulse wave parameters
        row +=35
        col = 2

        Label(wri, row, col, 'rise', fgcolor = BLUE)
        rise_lbl = Label(wri, row, col+50, 40, bdcolor=False, fgcolor=LIGHTGREY)
        rise_adj = Adjuster(wri, row, col+30, callback=rise_cb, fgcolor=BLUE, value=0.05)
        rise_adj.greyed_out(1)


        col = 110
        Label(wri, row, col, 'up', fgcolor = BLUE)
        up_lbl = Label(wri, row, col+40, 40, bdcolor=False, fgcolor=LIGHTGREY)
        up_adj = Adjuster(wri, row, col+20, callback=up_cb, fgcolor=BLUE, value=0.5)
        up_adj.greyed_out(1)

        col = 220
        Label(wri, row, col, 'fall', fgcolor = BLUE)
        fall_lbl = Label(wri, row, col+45, 40, bdcolor=False, fgcolor=LIGHTGREY)
        fall_adj = Adjuster(wri, row, col+25, callback=fall_cb, fgcolor=BLUE, value=0.05)
        fall_adj.greyed_out(1)

        #Parameter "width" for Gauss, Sinc, "expo" for Expo and "noiseq" for Noise
        # all will fill wave[pars][0] but have different ranges
        row +=30
        col = 2
        Label(wri, row, col, 'width', fgcolor = BLUE)
        width_lbl = Label(wri, row, col+60, 40, bdcolor=False, fgcolor=LIGHTGREY)
        width_adj = Adjuster(wri, row, col+40, callback=width_cb, fgcolor=BLUE, value=0.5)
        width_adj.greyed_out(1)

        col = 110
        Label(wri, row, col, 'expo', fgcolor = BLUE)
        expo_lbl = Label(wri, row, col+60, 30, bdcolor=False, fgcolor=LIGHTGREY)
        expo_adj = Adjuster(wri, row, col+35, callback=expo_cb, fgcolor=BLUE, value=0.49)
        expo_adj.greyed_out(1)

        col = 200
        Label(wri, row, col, 'noiseq', fgcolor = BLUE)
        noise_lbl = Label(wri, row, col+80, 30, bdcolor=False, fgcolor=LIGHTGREY)
        noise_adj = Adjuster(wri, row, col+45, callback=noise_cb, fgcolor=BLUE, value=0.5)
        noise_adj.greyed_out(1)


        # Setup button to start the AWG, stop button to stop output of the AWG
        col = 80
        row = 210
        start_stop = ButtonList(callback=startstop_cb)
        for t in table_startstop_buttons:
            start_stop.add_button(wri, row, col, textcolor = WHITE, **t)

    
        # Display calculated frequency in bottom right corner
        col = 210
        Label(wri, row-2, col+10, 'Frequency out:', fgcolor = ORANGE)
        fout_lbl = Label(wri, row+14, col+10, 90,fgcolor = ORANGE)
        fout_lbl.value('0' + 'Hz')


try:
    gc.collect() # precaution to free up unused RAM
    print('0: starting ui, mem: ', gc.mem_free())
    #run the ui

    Screen.change(BaseScreen)

except KeyboardInterrupt:
    print('0: Got ctrl-c')
    stopDMA()

except Exception as e:
    print('0: mainloop crashed: ', e)

finally:
        print('0: finally: cleaning up')
        stopDMA()
        #sys.exit()
