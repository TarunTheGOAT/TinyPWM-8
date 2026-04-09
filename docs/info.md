<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

I2C is a synchronous, multi-master, multi-slave serial bus. In our project, the chip acts as a Slave. It listens to the "Master" (usually a microcontroller) to know what duty cycle to set.
Inputs: 
SDA (Serial Data) and SCL (Serial Clock): The Master toggles SCL and places data on SDA.

Start Condition: The Master pulls SDA low while SCL is high. This "wakes up" the state machine.

Addressing: The first 7 bits sent are the address. The code compares this to the hardcoded address (e.g., 7'h3C). If they match, your chip sends an ACK (Acknowledge) by pulling SDA low on the 9th clock pulse.

Register Selection & Data: The Master sends a "Register Address" (to choose between Duty Cycle or Prescaler) and then the "Data Value." Your shift_reg collects these bits one by one and, once 8 bits are received, transfers them to the internal registers.

Pulse Width Modulation (PWM) is a way of simulating an analog voltage using a digital signal. It works by switching the output ON and OFF very quickly.

The Counter: A free-running 8-bit counter (let's call it pwm_cnt) counts from 0 to 255 and then overflows back to 0. This defines the Frequency.

The Comparator: It compares the current value of pwm\_cnt against your programmed duty\_cycle register.

If pwm\_cnt < duty\_cycle, the output pin goes HIGH.

If pwm\_cnt >= duty\_cycle, the output pin goes LOW.

Thus by changing the value in the duty_cycle register via I2C, you change how long the signal stays HIGH versus LOW.

8'h80 (128 decimal) results in a 50% duty cycle.

8'hFF (255 decimal) results in a near 100% duty cycle.

## How to test

## External hardware

To view the output of this project, you will need:

