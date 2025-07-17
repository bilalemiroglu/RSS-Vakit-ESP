# RSS-Vakit-ESP
This code written in Micropython runs on the LilyGo ESP32 T3 v1.6.1 and fetches the current prayer times for Istanbul from the RSS feed of the namazvakti.com website, then displays them on the OLED screen. 

If it is not possible to connect to a nearby hotspot, it uses the module's AP feature to allow entering a new SSID through a web service it creates. When there is a registered SSID in its memory, at startup it directly downloads the RSS feed and starts showing the prayer times.

The Python code has been designed for an ESP32 development board running MicroPython that establishes a Wi-Fi connection, synchronizes the time from an NTP server, and retrieves prayer times from a specific RSS source (namazvakti.com) to display them on an OLED screen. 
The code is developed specifically for the ESP32 development board running MicroPython. 
The device connects to a configured Wi-Fi network, obtains the correct time from the NTP server, and fetches the current prayer times from the RSS source to display them on the OLED screen.
Errors that may occur during Wi-Fi connection, NTP synchronization, or RSS retrieval are handled by providing information to the user on the screen, ensuring that the program continues to run smoothly.
