# pixel-pi Setup Guide

Getting from a blank SD card to a running pixel art display.

**Assumes:** The code is already written and in this repo. This guide covers OS setup, display driver, dependencies, and running as a service.

**Time required:** ~45 minutes on a good day.

---

## What you need

- Raspberry Pi Zero 2W (recommended), Zero 1, or Pi 4
- Waveshare 3.5" SPI display HAT
- MicroSD card (8GB minimum, 16GB+ recommended)
- Power supply for your Pi model
- Another computer to flash the SD card and SSH from
- Your local Wi-Fi credentials

---

## Step 1 — Flash the OS

1. Download and install **Raspberry Pi Imager**: https://raspberrypi.com/software

2. In Imager:
   - **Device:** choose your Pi model
   - **OS:** Raspberry Pi OS Lite (64-bit for Zero 2W / Pi 4, 32-bit for Zero 1)
     - Find it under *Raspberry Pi OS (other)*
     - Lite = no desktop, which is what we want
   - **Storage:** your SD card

3. Click **Next**, then when prompted click **Edit Settings** (the gear icon):

   - **General tab:**
     - Hostname: `pixel-pi`
     - Username: `pi` (or your preference)
     - Password: set something
     - Wi-Fi SSID and password: your network
     - Wi-Fi country: SE
   - **Services tab:**
     - Enable SSH ✓
     - Use password authentication

4. Save, click **Yes** to apply, then write the image.

5. Insert SD card into Pi, connect the display HAT, power on.

6. Wait 60–90 seconds for first boot, then SSH in:

   ```bash
   ssh pi@pixel-pi.local
   ```

   If `pixel-pi.local` doesn't resolve, find the IP from your router's device list and use that instead.

---

## Step 2 — System update

Before anything else:

```bash
sudo apt update && sudo apt upgrade -y
```

This takes a few minutes. Reboot when done:

```bash
sudo reboot
```

SSH back in after ~30 seconds.

---

## Step 3 — Enable SPI

The display communicates over SPI. Enable it:

```bash
sudo raspi-config
```

Navigate to: **Interface Options → SPI → Yes → OK**

Then: **Finish** (don't reboot yet, more config coming).

---

## Step 4 — Set the framebuffer resolution

The Pi needs to output at 480×320 to match the display. Edit the boot config:

```bash
sudo nano /boot/firmware/config.txt
```

> **Note:** On older OS versions the path is `/boot/config.txt` — check which exists if unsure.

Add these lines at the bottom:

```
# pixel-pi display config
hdmi_group=2
hdmi_mode=87
hdmi_cvt=480 320 60 1 0 0 0
hdmi_force_hotplug=1
```

Save with `Ctrl+O`, `Enter`, then `Ctrl+X`.

Now reboot:

```bash
sudo reboot
```

---

## Step 5 — Install the SPI display driver

The Waveshare HAT shows up as a Linux framebuffer device (`/dev/fb1`). The `fbcp-ili9341` driver copies the main framebuffer to the display over SPI efficiently, using partial updates so it doesn't saturate the bus.

```bash
# Install build tools
sudo apt install -y cmake git build-essential

# Clone the driver
cd ~
git clone https://github.com/juj/fbcp-ili9341.git
cd fbcp-ili9341
mkdir build && cd build
```

Now build with the correct flag for your display. **Check your Waveshare model:**

| Model | Controller | Build flag |
|---|---|---|
| 3.5inch RPi LCD (A) | ILI9486 | `-DWAVESHARE35B_ILI9486=ON` |
| 3.5inch RPi LCD (B) | ILI9486 | `-DWAVESHARE35B_ILI9486=ON` |
| 3.5inch RPi LCD (C) | ILI9486 | `-DWAVESHARE35B_ILI9486=ON` |

If unsure, check the Waveshare wiki page for your specific model. The controller chip is listed in the specs.

```bash
cmake -DWAVESHARE35B_ILI9486=ON \
      -DSPI_BUS_CLOCK_DIVISOR=6 \
      -DSTATISTICS=0 \
      ..
make -j$(nproc)
```

> `SPI_BUS_CLOCK_DIVISOR=6` gives a safe clock speed. If you get display flicker later, try increasing to `8`. If it's stable and you want to push it, try `4`.

Test it immediately:

```bash
sudo ./fbcp-ili9341
```

The display should light up and mirror the console. If it works, `Ctrl+C` to stop — we'll set it up as a service next.

**Install and enable as a service:**

```bash
sudo cp fbcp-ili9341 /usr/local/bin/

sudo tee /etc/systemd/system/fbcp.service > /dev/null <<EOF
[Unit]
Description=fbcp SPI display driver
After=multi-user.target

[Service]
ExecStart=/usr/local/bin/fbcp-ili9341
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable fbcp
sudo systemctl start fbcp
```

Verify it's running:

```bash
sudo systemctl status fbcp
```

---

## Step 6 — Verify the framebuffer devices

```bash
ls -la /dev/fb*
```

You should see both `/dev/fb0` (main framebuffer) and `/dev/fb1` (the SPI display). If only `/dev/fb0` exists, SPI is not enabled correctly — go back to Step 3.

---

## Step 7 — Install Python dependencies

```bash
# System packages (prefer apt for pygame — pip version can have issues on Pi)
sudo apt install -y python3-pip python3-pygame python3-dev python3-venv

# Create a virtual environment in the project directory
cd ~
git clone https://github.com/sylten/pixelscene.git pixel-pi
cd pixel-pi

python3 -m venv venv --system-site-packages
# --system-site-packages lets us use the system pygame inside the venv

source venv/bin/activate
pip install -r requirements.txt
```

> The `--system-site-packages` flag is important — it lets the venv use the system-installed `pygame` which is compiled for the Pi's architecture. Installing `pygame` via pip on a Pi Zero can take 20+ minutes or fail entirely.

---

## Step 8 — Configure pixel-pi

```bash
cp config.example.py config.py
nano config.py
```

Key settings to verify:

```python
DISPLAY_DRIVER = "fbcp"       # Use "sdl" for desktop development
FRAMEBUFFER = "/dev/fb1"      # Should match what you saw in Step 6
HTTP_PORT = 5000
HTTP_HOST = "0.0.0.0"
TARGET_FPS = 12
```

Save and exit.

---

## Step 9 — Test run

Run manually first to confirm everything works before setting up autostart:

```bash
source venv/bin/activate
python3 main.py
```

The display should show the overworld scene with ambient animations running.

**From another terminal on your computer**, test an event:

```bash
curl -X POST http://pixel-pi.local:5000/event \
  -H "Content-Type: application/json" \
  -d '{"event": "sale"}'
```

You should see the sale animation play on the display.

Check the health endpoint:

```bash
curl http://pixel-pi.local:5000/health
```

Expected response:
```json
{ "status": "ok", "scene": "overworld", "queue_depth": 0 }
```

If everything works, `Ctrl+C` to stop.

---

## Step 10 — Run as a service

```bash
sudo tee /etc/systemd/system/pixel-pi.service > /dev/null <<EOF
[Unit]
Description=pixel-pi animation server
After=network-online.target fbcp.service
Wants=network-online.target

[Service]
WorkingDirectory=/home/pi/pixel-pi
ExecStart=/home/pi/pixel-pi/venv/bin/python3 main.py
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable pixel-pi
sudo systemctl start pixel-pi
```

Check it's running:

```bash
sudo systemctl status pixel-pi
```

Watch live logs:

```bash
journalctl -u pixel-pi -f
```

---

## Step 11 — Assign a static local IP

So that digipi can always reach pixel-pi, give it a fixed local IP. The cleanest way is a **DHCP reservation** in your router:

1. Find pixel-pi's MAC address:
   ```bash
   ip link show wlan0
   ```
   The MAC is the `link/ether` value, e.g. `b8:27:eb:xx:xx:xx`

2. In your router admin panel (usually `192.168.1.1`), find the DHCP/LAN settings and add a reservation binding that MAC to a fixed IP, e.g. `192.168.1.50`.

3. Reboot pixel-pi to pick up the new lease:
   ```bash
   sudo reboot
   ```

4. Verify:
   ```bash
   ip addr show wlan0
   ```

---

## Step 12 — Connect digipi

On the digipi side, add the pixel-pi URL to its config and add the HTTP notify call to the event handler. See `SPEC.md` — **digipi Integration** section for the exact code.

After deploying to digipi, trigger a real business event and confirm both displays react.

---

## Updating pixel-pi

To pull new code and restart:

```bash
cd ~/pixel-pi
git pull
sudo systemctl restart pixel-pi
```

---

## Troubleshooting

**Display stays black after boot**

Check fbcp is running:
```bash
sudo systemctl status fbcp
journalctl -u fbcp -n 50
```

If it crashed, check for SPI errors. Try a higher `SPI_BUS_CLOCK_DIVISOR` (rebuild with `8` instead of `6`).

---

**`/dev/fb1` doesn't exist**

SPI is not enabled. Go back to Step 3 (`raspi-config → Interface Options → SPI`). Also confirm the HAT is fully seated on the GPIO pins.

---

**`pixel-pi.local` doesn't resolve**

Try the IP address directly. On some networks mDNS doesn't propagate. You can also install avahi:
```bash
sudo apt install -y avahi-daemon
```

---

**pygame errors on startup**

If you see `pygame.error: No available video device`:
```bash
# Check the framebuffer exists
ls /dev/fb*

# Try setting SDL to use the framebuffer
export SDL_VIDEODRIVER=fbcon
export SDL_FBDEV=/dev/fb1
python3 main.py
```

If this fixes it, add those env vars to the systemd service file under `[Service]`:
```
Environment=SDL_VIDEODRIVER=fbcon
Environment=SDL_FBDEV=/dev/fb1
```

---

**Animations feel slow / choppy**

On a Zero 1, reduce ambient layer complexity. Check CPU usage:
```bash
top
```

If the Python process is consistently above 80% CPU, reduce `TARGET_FPS` in `config.py` to `8` and simplify the scene (fewer scroll layers, smaller sprites).

---

**HTTP endpoint not reachable from digipi**

Check Flask is binding to `0.0.0.0` (not `localhost`) in `config.py`. Check the Pi's firewall:
```bash
sudo ufw status
```

If ufw is active, allow port 5000:
```bash
sudo ufw allow 5000/tcp
```

---

## Development on Desktop (no Pi needed)

Set `DISPLAY_DRIVER = "sdl"` in `config.py`. This renders to a 480×320 window on your Mac or Linux machine. The HTTP server runs normally — POST events with curl to test animations.

```bash
# On your dev machine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

This is the recommended way to build and iterate on sprite animations and event sequences before deploying to the Pi.
