#!/usr/bin/python3
import smbus
import RPi.GPIO as GPIO
import os
import sys
import time
import psutil
import json
import os
import subprocess
from threading import Thread
import paho.mqtt.client as mqtt
import yaml

rev = GPIO.RPI_REVISION

if rev == 2 or rev == 3:
	bus = smbus.SMBus(1)
else:
	bus = smbus.SMBus(0)

MQTT_CLIENT = os.uname()[1] + "_stats"

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
shutdown_pin=4
GPIO.setup(shutdown_pin, GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)


class Config:
    def __init__(self, configfile):
        defaultfan = [{65: 100}, {60: 55}, {55: 10}]
        with open(configfile) as file:
            self._config = yaml.load(file, Loader=yaml.FullLoader)
            mqtt = self._config.get('mqtt', {})
            self._server = mqtt.get('server', 'localhost')
            self._port = mqtt.get('port', 1883)
            self._topic = mqtt.get('topic', 'homeassistant/status/%%hostname%%')
            self._topic = self._topic.replace('%%hostname%%', os.uname()[1].lower())
            self._temps = self._config.get('fan', defaultfan)
            try:
                self._temps.sort(reverse=True, key=lambda x: (list(x.keys()))[0])
                for s in self._temps:
                    int(s[list(s.keys())[0]])
            except:
                print(f'Fan values are invalid: {sys.exc_info()[1]} - using deaults')
                self._temps = defaultfan
                self._temps.sort(reverse=True, key=lambda x: (list(x.keys()))[0])
            self._lowtemp = list(self._temps[len(self._temps) - 1].keys())[0]

    def get_topic(self):
        return self._topic

    def get_port(self):
        return self._port
    
    def get_server(self):
        return self._server

    def get_speed(self, temp):
        if temp < self._lowtemp:
            return 0
        for s in self._temps:
            if temp >= list(s.keys())[0]:
                return s[list(s.keys())[0]]
        return 0

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
	fanconfig = Config("/etc/argond_config.yaml")

	client = mqtt.Client(MQTT_CLIENT)
	client.loop_start()
	try:
		client.connect(fanconfig.get_server(), fanconfig.get_port())
	except:
		print(f'Failed to connect to MQTT server: {sys.exc_info()[1]}')
	
	readings = {}

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
		block = fanconfig.get_speed(val)
		if block < prevblock:
			time.sleep(30)
		prevblock = block
		try:
			bus.write_byte(address, block)
		except IOError:
			temp=""
		readings["fanspeed"] = block
		if client.is_connected():
			client.publish(fanconfig.get_topic(), json.dumps(readings))
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
