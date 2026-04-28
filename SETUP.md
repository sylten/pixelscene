# pixel-pi Setup Guide

Getting from a blank SD card to a running pixel art display.

**Assumes:** The code is already written and in this repo. This guide covers OS setup, display driver, dependencies, and running as a service.

**Time required:** ~1 hour.

---

## Important notes before you start

**OS:** You must use **Raspberry Pi OS Lite (32-bit) — Bookworm**. Do not use 64-bit, and do not use Trixie (Debian 13) or newer. The SPI display driver requires Broadcom userland libraries removed in later releases.

**Display output:** This setup does NOT use SDL's display driver. pygame draws to an in-memory surface and we write frames directly to `/dev/fb0` via mmap. This is intentional — SDL 2 on Bookworm does not include fbcon support, and direct framebuffer writes are fast enough for 12fps pixel art.

**fbcp-ili9341:** Must be built with `-DUSE_DMA_TRANSFERS=OFF` on this hardware. DMA conflicts with the firmware framebuffer setup.

---

## What you need

- Raspberry Pi (2, Zero 2W, or Pi 4 — this guide was tested on a Pi 2 Model B)
- Waveshare 3.5" SPI display HAT
- MicroSD card (8GB minimum, 16GB+ recommended)
- Power supply
- Another computer to flash and SSH from
- Your local Wi-Fi credentials

---

## Step 1 — Flash the OS

1. Download **Raspberry Pi Imager**: https://raspberrypi.com/software

2. In Imager:
   - **Device:** your Pi model
   - **OS:** Click **Raspberry Pi OS (other)** → **Raspberry Pi OS Lite (32-bit)**
     - Confirm the description says **Bookworm** — if it says Trixie, keep looking
   - **Storage:** your SD card

3. Click **Next** → **Edit Settings**:

   - **General tab:**
     - Hostname: `pixel-pi`
     - Username: `pi`
     - Password: something memorable
     - Wi-Fi SSID and password
     - Wi-Fi country: SE
   - **Services tab:**
     - Enable SSH ✓
     - Paste your public key (`cat ~/.ssh/id_ed25519.pub` on your Mac), or use password auth

4. Write the image, eject, insert into Pi, attach the display HAT, power on.

5. Wait 60–90 seconds, then SSH in:

   ```bash
   ssh pi@pixel-pi.local
   ```

   If that doesn't resolve, find the IP from your router and use it directly.

> **After reflashing**, if you get a "host key changed" SSH warning:
> ```bash
> sed -i '' '/pixel-pi/d' ~/.ssh/known_hosts
> ```

---

## Step 2 — Verify the OS

```bash
cat /etc/os-release
```

Must show `VERSION_CODENAME=bookworm`. If it says `trixie` — reflash.

```bash
uname -m
```

Must return `armv7l`. If it returns `aarch64` — reflash with the 32-bit image.

---

## Step 3 — System update

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

SSH back in after ~30 seconds.

---

## Step 4 — Enable SPI

```bash
sudo raspi-config
```

**Interface Options → SPI → Yes → OK → Finish**

---

## Step 5 — Configure `/boot/firmware/config.txt`

Replace the entire file with this known-working configuration:

```bash
sudo tee /boot/firmware/config.txt > /dev/null << 'EOF'
# For more options and information see
# http://rptl.io/configtxt

#dtparam=i2c_arm=on
#dtparam=i2s=on
dtparam=spi=on

dtparam=audio=on

camera_auto_detect=1
display_auto_detect=1
auto_initramfs=1

# vc4 driver commented out — required for fbcp and direct framebuffer access
#dtoverlay=vc4-fkms-v3d
max_framebuffers=2

disable_overscan=1
arm_boost=1

gpu_mem=64

[cm4]
otg_mode=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]

# pixel-pi display config
hdmi_group=2
hdmi_mode=87
hdmi_cvt=480 320 60 1 0 0 0
hdmi_force_hotplug=1
hdmi_ignore_edid=0xa5000080
EOF
```

> **Why is vc4-fkms-v3d commented out?** The vc4 KMS driver takes exclusive ownership of the framebuffer, preventing both fbcp and pygame's direct framebuffer writes from working. Without it, the firmware creates a simple framebuffer that everything can access freely.

Reboot:

```bash
sudo reboot
```

---

## Step 6 — Verify the framebuffer

```bash
ls /dev/fb*
```

Should show `/dev/fb0`. If nothing appears, SPI or the boot config isn't set correctly — recheck Steps 4 and 5.

---

## Step 7 — Build and install the SPI display driver

`fbcp-ili9341` copies the framebuffer to the SPI display. It must be built with DMA disabled and specific channel settings for this hardware.

```bash
sudo apt install -y cmake git build-essential libraspberrypi-dev

cd ~
git clone https://github.com/juj/fbcp-ili9341.git
cd fbcp-ili9341
mkdir build && cd build

cmake -DWAVESHARE35B_ILI9486=ON \
      -DSPI_BUS_CLOCK_DIVISOR=6 \
      -DSTATISTICS=0 \
      -DUSE_DMA_TRANSFERS=OFF \
      ..
make -j$(nproc)
```

> **Why `-DUSE_DMA_TRANSFERS=OFF`?** DMA transfers conflict with the firmware framebuffer on this hardware configuration and cause fbcp to crash on startup.

Test it:

```bash
sudo ./fbcp-ili9341
```

You should see the console login prompt appear on the display. `Ctrl+C` to stop.

Install as a service:

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
sudo systemctl status fbcp
```

Status should show `active (running)`.

---

## Step 8 — Verify the display pipeline

Test that pygame can draw to the framebuffer:

```bash
sudo apt install -y python3-pygame

python3 -c "
import pygame, mmap, time

pygame.init()
screen = pygame.Surface((480, 320))
screen.fill((255, 0, 0))

fb = open('/dev/fb0', 'rb+')
fb_map = mmap.mmap(fb.fileno(), 480 * 320 * 4, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
raw = pygame.image.tostring(screen, 'RGBX')
fb_map.seek(0)
fb_map.write(raw)
time.sleep(3)

screen.fill((0, 255, 0))
raw = pygame.image.tostring(screen, 'RGBX')
fb_map.seek(0)
fb_map.write(raw)
time.sleep(3)

fb_map.close()
fb.close()
pygame.quit()
"
```

You should see the display turn red, then green. If that works, the full pipeline is confirmed.

> **Note:** We do NOT use `pygame.display.set_mode()` or `SDL_VIDEODRIVER`. SDL 2 on Bookworm does not include fbcon support. Instead, pygame draws to a `pygame.Surface` and we write frames directly to `/dev/fb0` via mmap. The game engine handles this transparently.

---

## Step 9 — Install Python dependencies

```bash
sudo apt install -y python3-pip python3-pygame python3-dev python3-venv

cd ~
git clone https://github.com/sylten/pixelscene.git pixel-pi
cd pixel-pi

python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt
```

> `--system-site-packages` lets the venv use the apt-installed pygame, which is pre-compiled for ARM. Installing pygame via pip on a Pi can be very slow or fail.

---

## Step 10 — Configure pixel-pi

```bash
cp config.example.py config.py
nano config.py
```

Key settings:

```python
DISPLAY_DRIVER = "fb"         # Direct framebuffer — do not use "fbcon" or "sdl"
FRAMEBUFFER = "/dev/fb0"
HTTP_PORT = 5000
HTTP_HOST = "0.0.0.0"
TARGET_FPS = 12
```

---

## Step 11 — Test run

```bash
source venv/bin/activate
python3 main.py
```

The display should show the overworld scene. From your Mac, test an event:

```bash
curl -X POST http://pixel-pi.local:5000/event \
  -H "Content-Type: application/json" \
  -d '{"event": "sale"}'
```

Check health:

```bash
curl http://pixel-pi.local:5000/health
```

`Ctrl+C` when done.

---

## Step 12 — Run as a service

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
journalctl -u pixel-pi -f
```

---

## Step 13 — Static IP

Find the Pi's MAC address:

```bash
ip link show wlan0
```

In your router's admin panel, bind that MAC to a fixed IP. Reboot:

```bash
sudo reboot
```

---

## Step 14 — Connect digipi

Add the pixel-pi URL to digipi's config and add the HTTP notify call to its event handler. See `SPEC.md` — **digipi Integration** section.

---

## Updating

```bash
cd ~/pixel-pi
git pull
sudo systemctl restart pixel-pi
```

---

## Development on Desktop

The game renders to a `pygame.Surface` internally. For desktop development, set `DISPLAY_DRIVER = "sdl"` in `config.py` — this uses a normal pygame window instead of the framebuffer. The HTTP server works the same.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

---

## Troubleshooting

**Display stays black / no console on screen**

Check fbcp:
```bash
sudo systemctl status fbcp
journalctl -u fbcp -n 20
```

If it shows `Failed to allocate GPU memory` — make sure `gpu_mem=64` is in config.txt and `USE_DMA_TRANSFERS=OFF` was used when building.

---

**`bcm_host.h: No such file or directory` when building**

Wrong OS. Must be Bookworm 32-bit. Reflash.

---

**fbcp crashes with `DMA RX channel was in use`**

Rebuild with `-DUSE_DMA_TRANSFERS=OFF`. See Step 7.

---

**pygame draws but nothing appears on display**

Check fbcp is running (`sudo systemctl status fbcp`). Make sure `FRAMEBUFFER = "/dev/fb0"` in config.py.

---

**`/dev/fb0` missing after boot**

The vc4 driver may have been re-enabled. Check config.txt — `dtoverlay=vc4-fkms-v3d` must be commented out.

---

**`pixel-pi.local` doesn't resolve**

Use the IP directly, or:
```bash
sudo apt install -y avahi-daemon
```

---

**SSH host key warning after reflash**

```bash
sed -i '' '/pixel-pi/d' ~/.ssh/known_hosts
```

---

**HTTP not reachable from digipi**

Confirm `HTTP_HOST = "0.0.0.0"` in config.py. Check firewall:
```bash
sudo ufw status
# if active:
sudo ufw allow 5000/tcp
```
