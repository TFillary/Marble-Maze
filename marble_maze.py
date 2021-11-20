#!/usr/bin/env python3
#############################################################################
# Filename    : marble-maze.py
# Description :	Application to use the Pirate Audio board with 240x240 pixel screen + 4 buttons to
#               run a Marble Maze using a gyro/accelerometer board to control it.
#               Also uses a clever algorithm to generate new mazes (by Orestis Zekai - Fun With Python #1: Maze Generator)
#               Modified generated maze to create BMP & data files for the maze image
#               When run on Pi Zero, the marble position update was too slow, so used data array rather than 'pixels' 
#               access when checking for marble collisions.
#               Unfortunately still too slow, so modified Adafruit library functions for the display to be able to update either
#               the whole screen or only small parts to minimise the number of bytes sent to the display.
# Author      : Trevor Fillary
# modification: 04-08-2021
############################################################################

import smbus			#import SMBus module of I2C
import time
import math
import numpy as np
from pathlib import Path
from tdf_maze_generator import generate_new_maze, get_difficulty, set_difficulty

from gpiozero import Button

from colorsys import hsv_to_rgb
from PIL import Image, ImageDraw, ImageFont
from ST7789 import ST7789

# Definitions for gyro
#some MPU6050 Registers and their Address
PWR_MGMT_1   = 0x6B
SMPLRT_DIV   = 0x19
CONFIG       = 0x1A
GYRO_CONFIG  = 0x1B
INT_ENABLE   = 0x38
ACCEL_XOUT_H = 0x3B
ACCEL_YOUT_H = 0x3D
ACCEL_ZOUT_H = 0x3F
GYRO_XOUT_H  = 0x43
GYRO_YOUT_H  = 0x45
GYRO_ZOUT_H  = 0x47

# Definitions for the screen
SCREEN_SIZE = 240 # 240x240 square
MAX_SCREEN_INDEX = 239 # 0 to 239
MIN_SCREEN_INDEX = 0

# Definitions for marble shape
MARBLE_SIZE = 3 # 3x3 square
MARBLE_CORNER_OFFSET = 1  # Offset to calculate marble corners from centre x,y - DEPENDS ON MARBLE SIZE
# Calculate max screen indexes for marble size
MARBLE_MAX_SCREEN_INDEX = MAX_SCREEN_INDEX - MARBLE_CORNER_OFFSET
MARBLE_MIN_SCREEN_INDEX = MIN_SCREEN_INDEX + MARBLE_CORNER_OFFSET

# Set exit limit to determine completed - initial value, will change depending on maze size
exit_index_y = MAX_SCREEN_INDEX-3 

# Global image variables
pixels = 0
image = 0
image2 = 0
marble_x = 0
marble_y = 0
draw = 0

green_ball_image = Image.new("RGB", (3, 3), (0, 255, 0)) # green
black_ball_image = Image.new("RGB", (3, 3), (0, 0, 0)) # black

# Global state variables
PLAYING = 1
MAZE = 2
MENU = 3 
FINISHED = 4
GENERATE = 5
mode = MENU  # default to menu at start

# Incitialise global array ready for use
numpy_maze_data = []


def MPU_Init():
    #write to sample rate register
    bus.write_byte_data(Device_Address, SMPLRT_DIV, 7)

    #Write to power management register
    bus.write_byte_data(Device_Address, PWR_MGMT_1, 1)

    #Write to Configuration register
    bus.write_byte_data(Device_Address, CONFIG, 0)

    #Write to Gyro configuration register
    bus.write_byte_data(Device_Address, GYRO_CONFIG, 24)

    #Write to interrupt enable register
    bus.write_byte_data(Device_Address, INT_ENABLE, 1)


def read_raw_data(addr):
    # Accelero and Gyro value are 16-bit
    high = bus.read_byte_data(Device_Address, addr)
    low = bus.read_byte_data(Device_Address, addr+1)
    
    #concatenate higher and lower value
    value = ((high << 8) | low)
    
    #to get signed value from mpu6050
    if(value > 32768):
        value = value - 65536
    return value

def read_gyro_data():
    #Useful general routine NOT used in the game
    #Read Accelerometer raw value
    acc_x = read_raw_data(ACCEL_XOUT_H)
    acc_y = read_raw_data(ACCEL_YOUT_H)
    acc_z = read_raw_data(ACCEL_ZOUT_H)

    #Read Gyroscope raw value
    gyro_x = read_raw_data(GYRO_XOUT_H)
    gyro_y = read_raw_data(GYRO_YOUT_H)
    gyro_z = read_raw_data(GYRO_ZOUT_H)

    #Full scale range +/- 250 degree/C as per sensitivity scale factor
    Ax = acc_x/16384.0
    Ay = acc_y/16384.0
    Az = acc_z/16384.0

    Gx = gyro_x/131.0
    Gy = gyro_y/131.0
    Gz = gyro_z/131.0

    print ("Gx=%.2f" %Gx, u'\u00b0'+ "/s", "\tGy=%.2f" %Gy, u'\u00b0'+ "/s", "\tGz=%.2f" %Gz, u'\u00b0'+ "/s", "\tAx=%.2f g" %Ax, "\tAy=%.2f g" %Ay, "\tAz=%.2f g" %Az) 	

def read_gyro_xy():
    # Cut down routine to just read the x and y accelerometer values used in the game.  Return integers for direct x & y use
    #Read Accelerometer raw value
    acc_x = read_raw_data(ACCEL_XOUT_H)
    acc_y = read_raw_data(ACCEL_YOUT_H)

    #Full scale range +/- 250 degree/C as per sensitivity scale factor
    Ax = acc_x/16384.0      
    Ay = acc_y/16384.0

    if Ax >= 0:
        Dx = 1
    else:
        Dx = -1
    
    if Ay >= 0:
        Dy = 1
    else:
        Dy = -1
    
    #print (Ax, Ay, int(Dx), int(Dy))
    return int(Dx), int(Dy)  # return integer steps

def draw_menu():
    global image, draw
    image = Image.new("RGB", (SCREEN_SIZE, SCREEN_SIZE), (255, 255, 255)) # Make initial board white
    draw = ImageDraw.Draw(image) # Setup so can draw on the screen for menu etc.

        # Now to add some text for the buttons.....
    font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 16) # Create our font, passing in the font file and font size
    font2 = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 24) # Create our font, passing in the font file and font size

    # Rectangle for title
    draw.rectangle((40, 18, 200, 50), outline = ("black"))
    draw.text((50, 20), "Marble Maze", font = font2, fill = ("#eba414")) # Title

    txt_colour = (0,0,0) # black
    draw.text((5, 60), "Play", font = font, fill = txt_colour) # A button
    draw.text((5, 180), "Generate", font = font, fill = txt_colour) # B button
    draw.text((170, 60), "Tricky", font = font, fill = txt_colour)
    draw.text((170, 180), "Easy", font = font, fill = txt_colour)

    draw.text((190, 120), str(get_difficulty()+1), font = font2, fill = (0,255,0))
    draw.line((195, 80, 195, 120), width=4, fill=(255, 0, 0))
    draw.line((195, 150, 195, 180), width=4, fill=(255, 0, 0))

    image2 = Image.open("marble_pic.png")
    image2 = image2.resize((80,80)) 
    image.paste(image2, (60,80)) # onto menu screen

    # draw menu
    st7789.display(image)


def draw_completed(duration):
    global image, draw
    image = Image.new("RGB", (SCREEN_SIZE, SCREEN_SIZE), ("#99ccff")) # Make initial board bluish..
    draw = ImageDraw.Draw(image) # Setup so can draw on the screen for menu etc.

    # Success image
    image2 = Image.open("success.png")
    image2 = image2.resize((100,100)) 
    image.paste(image2, (70,10)) # onto screen

    # Now to add some text as well.....
    font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 24) # Create our font, passing in the font file and font size
    draw.text((20, 115), "Maze Completed", font = font, fill = ("red"))

    txt = "Time Taken: \n{:.2f}, seconds".format(duration)
    draw.text((20, 150), txt, font = font, fill = ("red"))

    # draw menu
    st7789.display(image)



def draw_maze():
    global image, image2, pixels, draw, exit_index_y, numpy_maze_data
    image = Image.new("RGB", (SCREEN_SIZE, SCREEN_SIZE), (0, 0, 0)) # Make initial board black
    pixels = image.load()  # Load image into memory for pixes access - check for collisions etc.
    image2 = Image.open("generated_maze.bmp") # Used bmp images to avoid jpeg compression artefacts
    image.paste(image2) # Paste generated maze onto screen
    draw = ImageDraw.Draw(image) # Setup so can draw marble on the screen

    # Read in maze datafile for the loaded bmp - Used in move_marble function
    numpy_temp = np.fromfile("generated_maze.dat",dtype=np.uint8)
    i = int(math.sqrt(len(numpy_temp)))  # calculate index size - always a square shape
    numpy_maze_data = numpy_temp.reshape(i, i)  # reset the maze to the correct 2D dimensions

    # Start marble in entrance in top row
    entrance_found = False
    for i in range(1,MAX_SCREEN_INDEX):
        if pixels[i,5] == (0,0,0):
            # Found entrance
            entrance_start_index_x = i
            entrance_found = True
            break

    for i in range(entrance_start_index_x, MAX_SCREEN_INDEX):
        if pixels[i,5] != (0,0,0):
            entrance_end_index_x = i
            break

    if not entrance_found:
        print ("Maze error")
        exit()
    
    initial_x = int((entrance_start_index_x + entrance_end_index_x)/2)
    initial_y = 5 # nominal 5 pixels in
    
    # Find highest y value - needed since the maze can vary in size depending on the resolution. Needed to work out when exit maze in main loop
    maze_found = False
    for i in range(MAX_SCREEN_INDEX,1,-1):
        if pixels[10,i] != (0,0,0):
            # Found the bottom edge of the maze
            exit_index_y = i-3  # need to allow for marble next position
            maze_found = True
            break

    if not maze_found:
        print ("Maze error")
        exit()

    # draw marble at initial location
    draw.rectangle((initial_x-MARBLE_CORNER_OFFSET, initial_y-MARBLE_CORNER_OFFSET, initial_x+MARBLE_CORNER_OFFSET, initial_y+MARBLE_CORNER_OFFSET), (0, 255, 0)) #  green pixels
    
    # draw playing area
    st7789.display(image)

    # return initial marble position in new maze
    return initial_x, initial_y


def move_marble(initial_mx,initial_my): # parameters are marblex and marbley
    global pixels, draw
    # Get latest change in position - in integer steps
    step_y, step_x = read_gyro_xy() # Note x & y swapped here due to orientation of sensor in the pi Zero case.

    # Use step details for new position
    next_mx = initial_mx - step_x
    next_my = initial_my - step_y

    # NOTE - maze has contiguous external walls so marble can only escapte via the entry or exit routes.  
    # check going back out the entry
    if next_my < MARBLE_MIN_SCREEN_INDEX:
        next_my = MARBLE_MIN_SCREEN_INDEX
    # check exit too otherwise collision checks may fail
    i, j = numpy_maze_data.shape
    if next_my > i:
        next_my = i

        # Check for collision with any 'non black' areas  # !!! NOTE HAD TO USE Y,X INSTEAD OF X,Y TO INDEX THE NUMPY ARRAY SINCE NUMPY USES ROW(Y), COL(X) INDEXING !!!!
    if (numpy_maze_data[next_my-MARBLE_CORNER_OFFSET, next_mx-MARBLE_CORNER_OFFSET] != 0 or numpy_maze_data[next_my+MARBLE_CORNER_OFFSET, next_mx-MARBLE_CORNER_OFFSET] != 0 or
        numpy_maze_data[next_my-MARBLE_CORNER_OFFSET, next_mx+MARBLE_CORNER_OFFSET] != 0 or numpy_maze_data[next_my+MARBLE_CORNER_OFFSET, next_mx+MARBLE_CORNER_OFFSET] != 0 ):
        # set back to last location
        next_mx = initial_mx
        next_my = initial_my
        # No need to update the display !!

    else: # Move normally....
        # First check if actually moved, if not then nothing more to do...
        if not (next_mx == initial_mx and next_my == initial_my):
            # Check screen bounds for marble size accordingly
            if (next_mx < MARBLE_MAX_SCREEN_INDEX) and (next_mx > MARBLE_MIN_SCREEN_INDEX) and next_my < MARBLE_MAX_SCREEN_INDEX and next_my > MARBLE_MIN_SCREEN_INDEX:
                # Delete existing marble - write a black block to the screen (not the full screen refresh to speed things up)
                st7789.display(black_ball_image,initial_mx-MARBLE_CORNER_OFFSET, initial_my-MARBLE_CORNER_OFFSET, initial_mx+MARBLE_CORNER_OFFSET, initial_my+MARBLE_CORNER_OFFSET)
                # draw marble at new location (not the full screen refresh to speed things up)
                st7789.display(green_ball_image,next_mx-MARBLE_CORNER_OFFSET, next_my-MARBLE_CORNER_OFFSET, next_mx+MARBLE_CORNER_OFFSET, next_my+MARBLE_CORNER_OFFSET)
            else: # Put back to last location 
                next_mx = initial_mx
                next_my = initial_my
                # No need to updaate the display !!
    
    return next_mx, next_my

def btn1handler():
    global mode
    # If playing a maze or finished a game, any button press will go back to the menu
    if mode == PLAYING or mode == FINISHED:
        mode = MENU
    else: # Menu option for button A is to play a maze
        mode = MAZE

def btn2handler():
    global mode
    # If playing a maze or finished a game, any button press will go back to the menu
    if mode == PLAYING or mode == FINISHED:
        mode = MENU
    else: # Menu option for button B is to generate a new maze
        mode = GENERATE

def btn3handler():
    global mode
    # If playing a maze or finished a game, any button press will go back to the menu
    if mode == PLAYING or mode == FINISHED:
        mode = MENU
    else: # Menu option for button X is to increase maze wall/corridor widths
        x = get_difficulty() + 1
        set_difficulty(x)


def btn4handler():
    global mode
    # If playing a maze or finished a game, any button press will go back to the menu
    if mode == PLAYING or mode == FINISHED:
        mode = MENU
    else: # Menu option for button X is to increase maze wall/corridor widths
        x = get_difficulty() - 1
        set_difficulty(x)

# Setup gyro object
bus = smbus.SMBus(1) 	# or bus = smbus.SMBus(0) for older version boards
Device_Address = 0x68   # MPU6050 device address
MPU_Init()

# Setup screen object
SPI_SPEED_MHZ = 80

st7789 = ST7789(
    rotation=90,  # Needed to display the right way up on Pirate Audio
    port=0,       # SPI port
    cs=1,         # SPI port Chip-select channel
    dc=9,         # BCM pin used for data/command
    backlight=13,
    spi_speed_hz=SPI_SPEED_MHZ * 1000 * 1000
)
# Button numbering is using BCM numbering
btn1 = Button(5)      # assign each button to a variable
btn2 = Button(6)      # by passing in the pin number
btn3 = Button(16)     # associated with the button
btn4 = Button(24)     # 

# tell the button what to do when pressed
btn1.when_pressed = btn1handler
btn2.when_pressed = btn2handler
btn3.when_pressed = btn3handler
btn4.when_pressed = btn4handler

mazefile = Path("generated_maze.dat")
if not mazefile.is_file():
# File does not exist so create initial maze otherwise will continue to use previous maze until a new one is generated manually.
    generate_new_maze()

while True:

    # Update marble position only if playing
    if mode == PLAYING:
        marble_x, marble_y = move_marble(marble_x, marble_y)

    elif mode == MENU:
        draw_menu()

    elif mode == MAZE:
        marble_x, marble_y = draw_maze()  # Initialise and draw maze
        mode = PLAYING
        game_start = time.time()

    elif mode == GENERATE:
        font = ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSans.ttf', 16) # Create our font, passing in the font file and font size
        draw.text((5, 180), "Generate", font = font, fill = "red") # B button
        # redraw menu
        st7789.display(image)
        generate_new_maze()
        mode = MENU
    
    if mode != FINISHED and marble_y >= exit_index_y:
        game_end = time.time()
        duration = game_end - game_start
        draw_completed(duration)
        mode = FINISHED
        # Make sure marble position setup for next run
        marble_x = 0
        marble_y = 0  

    #time.sleep(0.05)