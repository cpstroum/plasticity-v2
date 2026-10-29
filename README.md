# Vertebral Lumen — UNIHIKER LED controller

This program drives a 36-pixel WS2812B strip down a wearable costume's sternum. It is split into three replaceable layers:

- `costume_controller/hardware.py`: pinpong LED output plus normalized microphone, accelerometer, and gyro readings.
- `costume_controller/effects.py`: mode/effect rendering and pulse behavior; no UI or board-library dependencies.
- `costume_controller/ui.py`: UNIHIKER touchscreen controls and live indicators.

The touchscreen includes six selectable patterns: Flow, Spine Pulse, Motion Wake, Sound Ripple, Sound Bar, and Ember Field. The active mode determines whether motion, sound, or both influence the selected pattern.

The onboard light sensor automatically scales LED output for the room: the Bright setting remains the maximum, while darkness reduces the effective output. The light reading is smoothed to prevent sudden brightness jumps.

## Wiring and power

Use a separate regulated 5 V supply sized for the strip. Do not power the strip from the UNIHIKER. Connect the external supply ground to UNIHIKER ground. Route UNIHIKER D21 through a 74AHCT125 powered at 5 V, then through approximately 470 ohms in series to the WS2812B DIN pin. Use one UNIHIKER 3-pin GPIO port for signal and ground. Add a bulk capacitor near the strip if practical, and observe the strip's DIN/DOUT direction.

## Run

Copy this directory to the UNIHIKER and run:

```sh
python3 main.py
```

For development without the board:

```sh
python3 main.py --simulate
```

The initial palette is cyan `(0, 220, 220)` and violet `(150, 40, 220)`. `LED_COUNT` in `main.py` is the number of addressable WS2812 data nodes; change it if the strip has a different number. An RGB package contains three LED dies but counts as one addressable pixel. Sliders and mode buttons update the shared state immediately; no restart is required. If the installed UNIHIKER image exposes a different sensor method name, add that method name to the small probe lists in `hardware.py`.

## Copying the project to the UNIHIKER

When the UNIHIKER is connected directly by USB, its usual address is `10.1.2.3`. The board's default SSH account is `root` and the default password is `dfrobot`.

From PowerShell in this project directory, copy the files with:

```powershell
ssh root@10.1.2.3
scp -r .\* root@10.1.2.3:/root/plasticity-v2/
```

Then connect to the board and run the program:

```sh
ssh root@10.1.2.3
cd /root/plasticity-v2
python3 main.py
```

For repeated development, VS Code with the **Remote - SSH** extension is easier: connect to `root@10.1.2.3`, open `/root/plasticity-v2`, and edit or run `main.py` directly on the board. MobaXterm is another convenient option because it provides both an SSH terminal and a graphical file-transfer panel.
