#!/usr/bin/python3
import smbus
import RPi.GPIO as GPIO
import os
import time
import psutil
import json
import os
import subprocess
from threading import Thread
import paho.mqtt.client as mqtt

rev = GPIO.RPI_REVISION

if rev == 2 or rev == 3:
	bus = smbus.SMBus(1)
else:
	bus = smbus.SMBus(0)

TOPIC = "homeassistant/status/rr-hass"
MQTT_SERVER = "rr-api"
MQTT_PORT = 1883
MQTT_CLIENT = os.uname()[1] + "_stats"

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
shutdown_pin=4
GPIO.setup(shutdown_pin, GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)

def shutdown_check():
	while True:
		pulsetime = 1
		GPIO.wait_for_edge(shutdown_pin, GPIO.RISING)
		time.sleep(0.01)
		while GPIO.input(shutdown_pin) == GPIO.HIGH:
			time.sleep(0.01)
			pulsetime += 1
		if pulsetime >=2 and pulsetime <=3:
			os.system("reboot")
		elif pulsetime >=4 and pulsetime <=5:
			os.system("shutdown now -h")

def get_fanspeed(tempval, configlist):
	for curconfig in configlist:
		curpair = curconfig.split("=")
		tempcfg = float(curpair[0])
		fancfg = int(float(curpair[1]))
		if tempval >= tempcfg:
			return fancfg
	return 0

def load_config(fname):
	newconfig = []
	try:
		with open(fname, "r") as fp:
			for curline in fp:
				if not curline:
					continue
				tmpline = curline.strip()
				if not tmpline:
					continue
				if tmpline[0] == "#":
					continue
				tmppair = tmpline.split("=")
				if len(tmppair) != 2:
					continue
				tempval = 0
				fanval = 0
				try:
					tempval = float(tmppair[0])
					if tempval < 0 or tempval > 100:
						continue
				except:
					continue
				try:
					fanval = int(float(tmppair[1]))
					if fanval < 0 or fanval > 100:
						continue
				except:
					continue
				newconfig.append( "{:5.1f}={}".format(tempval,fanval))
		if len(newconfig) > 0:
			newconfig.sort(reverse=True)
	except:
		return []
	return newconfig

def get_readings():
    readings = {
        "gputemp": 0,
        "cputemp": 0,
        "useddisk": 0,
        "usedmem": 0,
        "cpuperc": 0
    }

    response = subprocess.run(['/opt/vc/bin/vcgencmd', 'measure_temp'], stdout=subprocess.PIPE)

    if response.returncode != 0:
        readings["gputemp"] = 0
    else:
        readings["gputemp"] = float(str(response.stdout, 'utf-8')[5 : -3])

    readings["useddisk"] = psutil.disk_usage('/').percent
    readings["usedmem"] = psutil.virtual_memory().percent
    readings["cpuperc"] = psutil.cpu_percent()
    return readings


def temp_check():
	fanconfig = ["65=100", "60=55", "55=10"]
	tmpconfig = load_config("/etc/argononed.conf")

	client = mqtt.Client(MQTT_CLIENT)
	client.loop_start()
	client.connect(MQTT_SERVER)
	
	readings = {
		"gputemp": 0,
		"cputemp": 0,
		"useddisk": 0,
		"usedmem": 0,
		"cpuperc": 0,
		"fanspeed": 0
	}

	if len(tmpconfig) > 0:
		fanconfig = tmpconfig
	address=0x1a
	prevblock=0
	while True:
		readings = get_readings()
		try:
			tempfp = open("/sys/class/thermal/thermal_zone0/temp", "r")
			temp = tempfp.readline()
			tempfp.close()
			val = float(int(temp)/1000)
		except IOError:
			val = 0
		readings["cputemp"] = val
		block = get_fanspeed(val, fanconfig)
		if block < prevblock:
			time.sleep(30)
		prevblock = block
		try:
			bus.write_byte(address, block)
		except IOError:
			temp=""
		readings["fanspeed"] = block
		client.publish(TOPIC, json.dumps(readings))
		time.sleep(30)

t1 = 0
t2 = 0
try:
	t1 = Thread(target = shutdown_check)
	t2 = Thread(target = temp_check)
	t1.start()
	t2.start()
except:
	t1.stop()
	t2.stop()
	GPIO.cleanup()
