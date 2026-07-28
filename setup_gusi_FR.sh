#!/bin/bash

# Les mp3 des stations ne sont plus telecharges a la main : updater.py les
# recupere depuis stations.json (voir la fin du script).

cd /root/gusi-radio
git stash
git pull
chmod 755 *.sh

echo "Stop MPD service"
sudo service mpd stop

echo "Moving files"
sudo cp /root/gusi-radio/shutdown /usr/local/bin/
sudo cp /root/gusi-radio/8192cu.conf /etc/modprobe.d/
sudo cp /root/gusi-radio/asound.conf /etc/
sudo cp /root/gusi-radio/mpd.conf /etc/
sudo cp /root/gusi-radio/FR/* /var/lib/mpd/music/
sudo cp /root/gusi-radio/cleanshutd.conf /etc/
sudo cp /root/gusi-radio/rc.local /etc/

echo "Configuring auto-update"
sudo mkdir -p /var/lib/gusi
sudo tee /var/lib/gusi/config.json > /dev/null <<'EOF'
{
  "language": "FR",
  "manifest_url": "https://raw.githubusercontent.com/EnhydraV/radiomichel/main/stations.json",
  "update_code": true
}
EOF

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
sudo chmod 755 /usr/local/bin/shutdown

echo "Start MPD service"
sudo systemctl enable mpd.service
sudo service mpd start

echo "Refresh MPD"
mpc update

echo "First update (stations + downloads)"
sudo python3 /root/gusi-radio/updater.py

echo "Installation finished. The device will reboot now."

sudo reboot 