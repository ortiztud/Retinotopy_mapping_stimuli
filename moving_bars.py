#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Retinotopic mapping: moving bars

Author: Michele Svanera
Nov. 2017
Modified by: Javier Ortiz-Tudela
May. 2021

- May 2021: The script will now wait for either a "t" or a "5" press.
- May 2021: The scripts will now prompt the user for participant info (credits to @felix_non for the first version.)
"""

################################################################################################################
## Imports 

from __future__ import division

from psychopy import visual, event, core, logging, gui
#from psychopy import gui  #fetch default gui handler (qt if available)
from psychopy import prefs as pyschopy_prefs

#from itertools import cycle  # import cycle if you want to flicker stimuli
#from psychopy.misc import pol2cart
#import copy
import numpy as np
import os
#import matplotlib.pyplot as plt
from datetime import datetime as dt
from time import gmtime, strftime
import threading


################################################################################################################
## Paths and Constants

EPSILON = 1e-5
serif = ['Times', 'Times New Roman']
sans = ['Gill Sans MT', 'Arial', 'Helvetica', 'Verdana']

# Button box
Initial_code = 16777200
Button_coding = [-1,-2,-3,-4,-5]            #red,yellow,green,blue,white(i.e. trigger)
IsMRI = 0                                   #MRI inverses the bit polarities
scanner_message = "Waiting for the scanner..."

# Experiment details
Fullscreen = True
Dir_save = 'D:/Mucklis_lab/Retinotopic_mapping/out/'
Log_name = 'LogFile.log'
Frames_durations_name = 'frames_durations.npy'
Fps_update_rate = 1                             # sec

# Bar properties
Flash_period = 0.2                              # seconds for one B-W cycle (ie 1/Hz)
Cycle_duration = 64                             # seconds for one passage
Bar_orientations = [x*45 for x in range(8)]     # Orientations
Bar_positions_number = 10000                    # Define the resolution (smoothness) of the movement 
Bar_paths = np.asarray([[[0,1],[0,-1]],[[1,1],[-1,-1]],[[1,0],[-1,0]],[[1,-1],[-1,1]],[[0,-1],[0,1]],[[-1,-1],[1,1]],
    [[-1,0],[1,0]],[[-1,1],[1,-1]]]) * 1.4
Bar_length = (1.,1./8.)                     # pix
Bar_orientation_order = np.array([1, 6, 3, 8, 5, 2, 7, 4])-1

# Fixation
Rotating_cross = False
Color_change_cross = True
Color_change_rate = 15                           # sec
Rotation_cross_rate = 0.05                      # revs per sec

# Spyder network
Spyder_grid = True
Spyder_rings = 4
Web_size = (1.,1.)

# External cover
External_ring_size = 2.5                          # unit='norm': diameter when shape='circle'

# Simulation (time) properties
Passagges_per_orientation = 1                   # Passagges every orientation
Pre_post_stimuli_fixation_time = 12.            # sec.
Total_time = Passagges_per_orientation * len(Bar_orientations) * Cycle_duration


################################################################################################################
## Functions

def screenCorrection(mywin,x):
    resX = mywin.size[0]
    resY = mywin.size[1]
    aspect = float(resX) / float(resY)

    if(Fullscreen == True):
        new = x / aspect
    else:
        new = x
    return(new)


def createOutFolder(path_out):
    if not os.path.exists(path_out):
        try:
            os.makedirs(path_out)
        except Exception as e:
            print('Problem with creating an *out* folder, check permissions: '+e)
    else:
        n_folder_name = 1
        path_out_new = path_out + "_" + str(n_folder_name)
        while(os.path.exists(path_out_new) is True):
            n_folder_name += 1
            path_out_new = path_out + "_" + str(n_folder_name)
        try:
            os.makedirs(path_out_new)
        except Exception as e:
            print('Problem with creating an *out* folder, check permissions: '+e)
        path_out = path_out_new
    path_out += '/'
    
    return path_out


class buttonBoxThread(threading.Thread):
    def __init__(self, thread_id, name):           
        threading.Thread.__init__(self)
        
        self.stimulus_onset_time = 0
        self.local_status = 0
        self.mask = 0x0000 if IsMRI == 0  else 0x001f
        
        # Open comunication with Vpixx
        DPxOpen()
        
        #Select the correct device
        DPxSelectDevice('PROPixxCtrl')
        DPxSetMarker()
        self.stimulus_onset_time = DPxGetMarker()
        DPxEnableDinDebounce()              # Filter out button bounce
        self.local_status = DPxSetDinLog()        # Configure logging with default values
        DPxStartDinLog()
        DPxUpdateRegCache()

        # Thread infos        
        self.thread_id = thread_id
        self.name = name
        
        # Every button has: its value {0,1} and time when it changed (as datetime)
        self.button_state = {'time': np.array([dt.now()]*5), 'state': np.zeros((5,),dtype=np.int8)}
        self.button_state['state'][-1] = 1
        self._stop_event = threading.Event()
        
    def run(self):
        logging.data("Starting " + self.name)
        
        initial_values = DPxGetDinValue()
        logging.data('Initial button box digital input states = ' + "{0:016b}".format(initial_values) + " (int=%d)".format(initial_values))

        while(True):
            DPxUpdateRegCache()
            DPxGetDinStatus(self.local_status)
            
            if self.local_status['newLogFrames'] > 0 :           #Something happened
                data_list = DPxReadDinLog(self.local_status)
                self.button_state = self.updateStateButton(self.button_state,data_list)
                
            if(self.stopped()):
                break
                
        logging.data("Exiting " + self.name)
        
    def stop(self):        
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()

    # Take in input a state and check what is changed
    def updateStateButton(self,button_state,data_list):   
        
        for j in range(len(data_list)):
            j_value = bin(data_list[j][1] ^ self.mask)
            
            # Check every button
            for i_button in range(len(button_state['state'])):
                i_button_detected_value = int(j_value[Button_coding[i_button]])
                if(i_button_detected_value != button_state['state'][i_button]):
                    button_state['state'][i_button] = i_button_detected_value
                    button_state['time'][i_button] = dt.now()

        return button_state
 
def rgb2gray(rgb):
    return np.dot(rgb[...,:3], [0.299, 0.587, 0.114])


    
################################################################################################################
## Main
    
def main(win, globalClock):
    
    all_changes = []
    
    ################################ Stimuli prepation ################################

    # Bar preparation    
    grating_texture = np.tile([[1,-1],[-1,1]], (1,12))#(4,64))
    grating_texture = np.dstack((grating_texture,grating_texture,grating_texture))
    bar_size = (Bar_length[0]*resX,Bar_length[1]*resY)
    grating_1 = visual.GratingStim(win,tex=grating_texture,color=[1.0, 1.0, 1.0],colorSpace='rgb', units="pix",
        size=bar_size,ori=0,autoLog=False,interpolate=False)
    grating_2 = visual.GratingStim(win,tex=~grating_texture+1,color=[1.0, 1.0, 1.0],colorSpace='rgb', units="pix",
        size=bar_size,ori=0,autoLog=False,interpolate=False)
    
    # Vertical shifting
    bar_positions = []
    for i_ori in range(len(Bar_orientations)):
        i_x = np.linspace(Bar_paths[i_ori,0,0],Bar_paths[i_ori,1,0],Bar_positions_number).reshape((-1,1))
        i_y = np.linspace(Bar_paths[i_ori,0,1],Bar_paths[i_ori,1,1],Bar_positions_number).reshape((-1,1))
        position_i = np.concatenate((i_x,i_y), axis=1)
        position_i = position_i * resY/2
        bar_positions.append(position_i)
    
    # Fixation cross preparation
    fixation = visual.ShapeStim(win,vertices=((0,-1),(0,1),(0,0),(-1,0),(1,0)),lineWidth=4, units="pix",
        size=(20,20),closeShape=False,lineColor='red',autoDraw=True)
    
    # Spyder network
    web_circle = visual.Circle(win=win,radius=1,edges=200,units='norm',pos=[0, 0],lineWidth=1,opacity=1,interpolate=True,
                            lineColor=[1.0, 1.0, 1.0],lineColorSpace='rgb',fillColor=None,fillColorSpace='rgb')
    web_dimension = (screenCorrection(win,Web_size[0]),Web_size[1])
    web_line = visual.Line(win,name='Line',start=(-1.4, 0),end=(1.4, 0),pos=[0, 0],lineWidth=1,
                           lineColor=[1.0, 1.0, 1.0],lineColorSpace='rgb',opacity=1,interpolate=True)

    # DEBUG stimuli
    if DEBUG_MODE:
        fps_text = visual.TextStim(win, units='norm', height=0.05,pos=(-0.98, +0.93), text='starting...',
                                  font=sans, alignHoriz='left', alignVert='bottom', color='yellow')    
        fps_text.autoDraw = True
        
        orientation_details_string = visual.TextStim(win, text = u"Orientation..", units='norm', height=0.05,
                                             pos=(0.95, +0.93), alignHoriz='right', alignVert='bottom', 
                                             font=sans, color='yellow')
        orientation_details_string.autoDraw = True        

    # External Aperture (black ring)
    external_aperture_size = tuple([screenCorrection(win,External_ring_size),External_ring_size])
    external_aperture = visual.Aperture(win, size=external_aperture_size, shape='circle')
    external_aperture.enabled = False

    ################################ Definitions/Functions ################################    
    
    ## handle Rkey presses each frame
    def escapeCondition():              
        for key in event.getKeys():
            if key in ['escape', 'q']:
                return False
        return True
    

    ################################ Animation starts ################################        
    # Display instructions and wait
    message1 = visual.TextStim(win, pos=[0,0.5],text='Hit a key when ready.')
    message1.draw()
    win.flip()
    event.waitKeys()    #pause until there's a keypress

    # Scanner trigger wait
    message3 = visual.TextStim(win,pos=[0,0.25],text=scanner_message,font=serif,alignVert='center',
                               wrapWidth=1.5)
    message3.size = .5
    message3.draw()
    win.flip()

    if BUTTON_BOX:
        button_state = button_thread.button_state
        while 1:
            if(button_state['state'][-1]==0):
                break
    else:
        event.waitKeys(keyList = ['5','t'])    #pause until 5 or t is pressed (scanner trigger)
  
    
    # Wait Pre_post_stimuli_fixation_time before stimuli
    # Spyder network
    if Spyder_grid:
        for i_dim in range(Spyder_rings):
            web_circle.setSize(tuple([x*(i_dim+1) * 1./Spyder_rings for x in web_dimension]))
            web_circle.draw()
        for i_dim in range(2):
            web_line.setOri(i_dim * 90)
            web_line.draw()
    win.flip()
    core.wait(Pre_post_stimuli_fixation_time)
    
    
    i_bar_ori = n_frame = last_fps_update = 0

    globalClock.reset()
    inizio = globalClock.getTime()
    timer_global = core.CountdownTimer(Total_time)    
    break_flag = True
    logging.data('First orientation. Number %d/%d at %f (sec.)' % (i_bar_ori+1,len(Bar_orientations),inizio))
    
    
    while (timer_global.getTime() > 0 and break_flag==True):                      #globalClock.getTime() < Total_time:
        n_frame += 1
        t = globalClock.getTime()

        # Spyder network
        if Spyder_grid:
            for i_dim in range(Spyder_rings):
                web_circle.setSize(tuple([x*(i_dim+1) * 1./Spyder_rings for x in web_dimension]))
                web_circle.draw()
            for i_dim in range(2):
                web_line.setOri(i_dim * 90)
                web_line.draw()

        # External ring
        external_aperture.enabled = True
                
        # Bar
        if (t >= ((i_bar_ori+1)*Cycle_duration*Passagges_per_orientation)) & (i_bar_ori < (len(Bar_orientations)-1)):
            i_bar_ori += 1
            logging.data('Change orientation. Number %d/%d at %f (sec.)' % (i_bar_ori+1,len(Bar_orientations),t))
            new_record = globalClock.getTime() - sum(all_changes)
            all_changes.append(new_record)        
        
        if t % Flash_period < Flash_period / 2.0:  # more accurate to count frames
            stim = grating_1
        else:
            stim = grating_2
        bar_pos_indx = int((Bar_positions_number / Cycle_duration) * (t % Cycle_duration) )
        i_orientation_ordered = Bar_orientation_order[i_bar_ori]
        stim.pos = tuple(bar_positions[i_orientation_ordered][bar_pos_indx])
        stim.ori = Bar_orientations[i_orientation_ordered]
        stim.draw()
        
                
        # Fixation
        if Rotating_cross:
            fixation.ori = t * Rotation_cross_rate * 360.0  # set new rotation
        if Color_change_cross:
            if t % Color_change_rate < Color_change_rate / 2.0:  # more accurate to count frames
                fixation.lineColor = 'red'
            else:
                fixation.lineColor = 'green'        

        external_aperture.enabled = False
        if DEBUG_MODE:
            if t - last_fps_update > Fps_update_rate:         # update the fps text every second
                fps_text.text = "%.2f fps" % win.fps()
                last_fps_update += 1
            orientation_details_string.text = 'Ori: %d/%d at %.3f (sec.)' % (i_bar_ori+1,len(Bar_orientations),np.sum(all_changes))

        # Update screen                
        win.flip()
        break_flag = escapeCondition()
        if break_flag == False: break
    

    logging.data('Total time spent: %.6f' % (globalClock.getTime() - inizio))
    logging.data('Every frame duration saved in %s' % (path_out+Frames_durations_name))
    logging.data('All durations: ' + str(all_changes))
    logging.data('Mean: ' + str(sum(all_changes)/(len(all_changes)+EPSILON)))

    if DEBUG_MODE:
        orientation_details_string.text = 'Ended at %.3f (sec.)' % (globalClock.getTime())

    win.flip()
    # Wait Pre_post_stimuli_fixation_time after stimuli
    core.wait(Pre_post_stimuli_fixation_time)
    return
    


if __name__ == "__main__":  
    
    # Open a dialog window and promt for participant info
    myDlg = gui.Dlg(title=" ")
    myDlg.addText('Participant info')
    myDlg.addField('Subject code:')
    myDlg.addField('Operator')
    participant_info = myDlg.show()
    
    # Experiment variables
    today_date = dt.today().strftime('%Y-%m-%d')        # Date (mm/dd/yy)
    operator = participant_info[1]                                    # Operator
    DEBUG_MODE = False                                   # Debug mode
    BUTTON_BOX = False                                   # Button box monitoring
    subject_code = participant_info[0]                            # Subject-code

    # Prepare out folder
    path_out = Dir_save + today_date + '_' + subject_code + '_bars'
    path_out = createOutFolder(path_out)

    if not os.path.exists(Dir_save):
        os.makedirs(Dir_save)
    globalClock = core.Clock()
    
    # Set the log module to report warnings to the standard output window
    logging.setDefaultClock(globalClock)
    logging.console.setLevel(logging.WARNING)
    lastLog=logging.LogFile(path_out+Log_name,level=logging.DATA,filemode='w',encoding='utf8')
    logging.data("------------- " + strftime("%Y-%m-%d %H:%M:%S", gmtime()) + " -------------")
    logging.data(pyschopy_prefs)
    logging.data("Saving in folder: " + path_out)
    logging.data("Operator: " + operator + "\n")    
    logging.data("Subject. Code: " + subject_code) 
    logging.data('***** Starting *****')

    # Create and start buttonBox thread
    if BUTTON_BOX:
        from pypixxlib._libdpx import DPxOpen, DPxSelectDevice, DPxSetMarker, \
            DPxUpdateRegCache, DPxGetMarker, DPxEnableDinDebounce, DPxGetDinValue, \
            DPxSetDinLog, DPxStartDinLog, DPxGetDinStatus, DPxReadDinLog
                   
        button_thread = buttonBoxThread(1, "button box check")
        button_thread.start()
        
    # Start window
    win = visual.Window([500,500], monitor="mon", screen=1, units="norm", fullscr=Fullscreen,
                        allowStencil=True) # norm
    resX,resY = win.size
    win.recordFrameIntervals = True

    # Main stimulation
    try:
        main(win, globalClock)
    except Exception as e:
        logging.log(e,level=logging.ERROR)

    # Stop buttonBox thread
    if BUTTON_BOX:
        button_thread.stop()
        
    logging.data('Overall, %i frames were dropped.' % win.nDroppedFrames)
    np.save(path_out+Frames_durations_name,win.frameIntervals[1:])
        
    logging.data('***** End *****')
    
    win.close()
    core.quit()


































