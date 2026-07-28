import subprocess
from gpiozero import Button, RotaryEncoder, LED
from signal import pause

import updater

# ---------- VAR DEFINITION ----------#
current_station = 0
vol = 30
btn_clk = RotaryEncoder(23, 27, max_steps=4)
btn_sw = Button(22)
led = LED(14)

# ---------- RADIO STATIONS ----------#
# Liste fournie par updater.py (manifeste JSON sur GitHub) : plus rien en dur.
stations = updater.load_stations()


# ---------- DEFINITIONS ----------#
def mpc(*arguments):
    # Pas de shell : les uri viennent d'un JSON distant.
    try:
        subprocess.call(["mpc"] + list(arguments), timeout=30)
    except (OSError, subprocess.SubprocessError) as error:
        print("mpc " + " ".join(arguments) + " failed: " + str(error))


def change_station():
    global current_station
    print("changing station from " + str(current_station))
    current_station = (current_station + 1) % len(stations)
    play(current_station)


def play(current_station):
    station = stations[current_station]
    print(str(station.get("name", "")) + " -> " + station["uri"])
    mpc("stop")
    mpc("clear")
    announcement = station.get("announcement")
    if announcement:
        mpc("add", announcement)
    mpc("add", station["uri"])
    mpc("play")


def vol_up():
    global vol
    if vol < 95:
        vol += 5
        if vol > 95:
            vol = 95
        print(str(vol))
        mpc("volume", str(vol))


def vol_down():
    global vol
    if vol > 0:
        vol -= 5
        if vol < 0:
            vol = 0
        print(str(vol))
        mpc("volume", str(vol))


# ---------- START ----------#
led.on()
mpc("clear")
mpc("repeat", "off")
mpc("volume", str(vol))
play(current_station)

btn_clk.when_rotated_clockwise = vol_up
btn_clk.when_rotated_counter_clockwise = vol_down
btn_sw.when_pressed = change_station

pause()
