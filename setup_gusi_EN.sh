#!/bin/bash

echo "Stop MPD service"
sudo service mpd stop

echo "Moving files"
sudo mv /root/gusi-radio/8192cu.conf /etc/modprobe.d/
sudo mv /root/gusi-radio/asound.conf /etc/
sudo mv /root/gusi-radio/mpd.conf /etc/
sudo mv /root/gusi-radio/EN/* /var/lib/mpd/music/
sudo mv /root/gusi-radio/cleanshutd.conf /etc/
sudo mv /root/gusi-radio/rc.local /etc/

echo "Cleaning up"
sudo rm -r /root/gusi-radio/DE
sudo rm -r /root/gusi-radio/EN
sudo rm -r /root/gusi-radio/.gitattributes
sudo rm -r /root/gusi-radio/.gitignore
sudo rm -r /root/gusi-radio/LICENSE
sudo rm -r /root/gusi-radio/README.md
sudo rm -r /root/gusi-radio/.git
sudo rm -r /root/gusi-radio/onoffshim
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