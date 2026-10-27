# Paltalk Room Opener

A Windows desktop app that invokes up to five named Paltalk room tiles in order.

`main.py` is the main entry point. Application code is organized in `paltalk_room_opener/` by responsibility: UI window, settings, worker thread, Windows UI Automation, and styling.

## Setup

Install Python 3.10 or newer, then in PowerShell from this folder run:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

## Use

1. Start Paltalk and display the My Rooms / Rooms view containing the room tiles. Keep the relevant tiles visible and Paltalk available while the app runs.
2. Enter the exact names exposed by the room tile buttons, in the desired order. For example: `XXX _ L_O_V_E _ _C_O_N_N_E_C_T_I_O_N _ XXX`. Leave unused entries blank.
3. Choose **Regular (3 rooms)** to open populated entries from Room 1–3, or **VIP (5 rooms)** to open populated entries from Room 1–5. Enable **Open when Paltalk starts** to run the selected room queue shortly after Paltalk starts; otherwise use **Open rooms** manually. Settings, including the selected mode and automatic-opening choice, are saved automatically and can also be saved using **Save settings**.
4. The app first queues every visible matching tile, then invokes the queued rooms in order. This lets it continue after Paltalk changes away from the Rooms view when the first room opens. Check the activity log for each invocation. **Stop** stops subsequent rooms, but cannot interrupt an invocation already in progress.

Room names and the delay are stored in `%APPDATA%\PaltalkRoomOpener\room_names.json` (under the current user's profile). The app finds Paltalk windows by process name, searches for exactly named UI Automation buttons, and invokes a matching button only when it is onscreen and has positive width. A successful invocation means the button was invoked; it does not independently verify that the room joined. If a room is not found, the app logs the failure and continues with the next room. Paltalk's layout, permissions, and navigation may affect which tiles are visible; return to the Rooms view if necessary.
