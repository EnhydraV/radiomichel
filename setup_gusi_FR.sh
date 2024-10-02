#!/bin/bash

echo "Stop MPD service"
sudo service mpd stop

echo "Moving files"
sudo cp /home/pi/gusi-radio/8192cu.conf /etc/modprobe.d/
sudo cp /home/pi/gusi-radio/asound.conf /etc/
sudo cp /home/pi/gusi-radio/mpd.conf /etc/
sudo cp /home/pi/gusi-radio/FR/* /var/lib/mpd/music/
sudo cp /home/pi/gusi-radio/cleanshutd.conf /etc/
sudo cp /home/pi/gusi-radio/rc.local /etc/

echo "Cleaning up"
sudo systemctl stop dphys-swapfile
sudo systemctl disable dphys-swapfile
sudo systemctl disable keyboard-setup.service
sudo systemctl disable triggerhappy.service
sudo /usr/bin/tvservice -o

echo "Set permission"
sudo chmod +x /etc/rc.local
sudo chmod -R g+w /var/lib/mpd
sudo chmod -R g+w /var/run/mpd

echo "Start MPD service"
sudo systemctl enable mpd.service
sudo service mpd start

echo "Refresh MPD"
mpc update

echo "Installation finished. The device will reboot now."

sudo reboot 