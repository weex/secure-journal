# Goal
A wifi-enabled mini-server with touchscreen-only setup to serve as a place to store and edit content securely. Think of it like a digital journal. Full-disk encryption, autoupdates using most secure OS possible, strong-password protected.

# Materials (with rough cost as of 1/2021):
- Raspberry Pi 3 $38.33
- 16gb microSD card $7.65
- Touchscreen module+case $26.25
- Power supply $7.65
- Total: $79.88

# Prototype setup procedure:
1. Get latest raspbian image
1. Flash with balenaetcher to microSD card
1. Mount flashed card on another system Ubuntu
1. On boot partition, create empty file named 'ssh' to enable ssh.
1. On root partition run the following:
    ```
    rm -r LCD-show/`
    git clone https://github.com/goodtft/LCD-show
    chmod -R 755 LCD-show/
    ```
1. Plug device into ethernet and boot up.
1. Find ip of device and login with username `pi` and password `raspberry`.
    ```
    ssh pi@xx.xx.xx.xx
    ```
1. Start Raspi-config
    ```
    sudo raspi-config
    ```
1. (in raspi-config) Set Wireless SSID and Password
1. (in raspi-config) Turn off graphical automatic login under System Options -> Boot / AutoLogin 
1. Finish LCD setup:
    ```
    cd LCD-show
    sudo ./LCD35-show
    ```
1. Reboot to complete setup

# Roadmap
- Create initial setup through touchscreen to setup wifi and choose strong password
- Add web-based app for taking notes with text formatting, image upload, versioned auto-save.
