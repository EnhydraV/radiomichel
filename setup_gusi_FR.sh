#!/bin/bash

cd /root/gusi-radio
git stash
git pull

echo "Stop MPD service"
sudo service mpd stop

echo "Moving files"
sudo rm /etc/modprobe.d/8192cu.conf
sudo ln -s /root/gusi-radio/8192cu.conf /etc/modprobe.d/8192cu.conf
sudo rm /etc/asound.conf
sudo ln -s /root/gusi-radio/asound.conf /etc/asound.conf
sudo rm  /etc/mpd.conf
sudo cp /root/gusi-radio/mpd.conf /etc/mpd.conf
sudo rm -rf /var/lib/mpd/music/
sudo ln -s /root/gusi-radio/FR /var/lib/mpd/music
sudo rm /etc/cleanshutd.conf
sudo ln -s /root/gusi-radio/cleanshutd.conf /etc/cleanshutd.conf
sudo rm /etc/rc.local
sudo ln -s /root/gusi-radio/rc.local /etc/rc.local

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