# ArgonOned
Adds MQTT to the Argon One service script

Since this script always runs on my Raspberry Pi to turn on the built in fan in the Argon One case it seemed like a good idea to extend it to provide some additional functionality. It reports cpu temperature, gpu temperature, percentage of used disk space, percentage of used virtual memory, cpu load and the fan state. This is all packaged into a single JSON string and published to a MQTT server. 

My Home Assistant instance subscribes to that topic and update MQTT sensors based upon the information in the JSON string.

## To Do
Still need to rewrite the configuration file reader function to also parse out the MQTT host name, port, topic, user identity and password.
