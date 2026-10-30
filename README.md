# Paltalk Room Opener

A Windows desktop app that invokes up to five named Paltalk room tiles in order.

`main.py` is the main entry point. Application code lives in `paltalk_automation/`, with feature folders for room opening, camera opening, advert blocking, admin actions, and the mic timer. Each feature has `ui_tabs/` and `backend/` folders; shared window, settings, workers, and styling remain at the package level.

## Setup

Install the 64-bit CPython 3.14 release, then in PowerShell from this folder run:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" -m pip install -r requirements.txt
& "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" main.py
```

Use the same Python 3.14 interpreter to install dependencies, run the app, and build the executable. Do not add the entire project folder as data; the Python source is collected by PyInstaller. Include the app's required non-Python resources, such as `paltalk_automation/camera_opener/backend/windows_ocr.ps1`.

Build a windowed executable with the helper modules and Windows automation library included:

```powershell
$python = "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"
& $python -m PyInstaller --noconfirm --onefile --windowed --name "Paltalk Automation" --icon "Icons/Paltalk Automation.ico" --hidden-import clr --add-data "Icons/Paltalk Automation.ico;Icons" --add-data "paltalk_automation/camera_opener/backend/windows_ocr.ps1;paltalk_automation/camera_opener/backend" main.py
```

The executable is created in `dist`. Quit any running copy from the notification area before replacing it or pinning the new executable.

The **Advert Blocker** tab enables an opaque overlay over Paltalk's advert area. Its on/off setting is remembered in `app_state.json`, and the overlay continues while the app is in the tray. The overlay follows the original Paltalk Advert Overlay's window-relative layout and blocks clicks in the covered area. It starts off until enabled.

The selected tab is restored on startup and stored in `%LOCALAPPDATA%\PaltalkRoomOpener\app_state.json`.

## Use

Closing the window keeps the app running in the Windows notification area, including any active monitoring. Click the tray icon or choose **Open Paltalk Automation** from its menu to restore the window. Choose **Quit** from the tray menu to stop background work and exit. If the system tray is unavailable, closing the window exits normally.

1. Start Paltalk and display the My Rooms / Rooms view containing the room tiles. Keep the relevant tiles visible and Paltalk available while the app runs. Opening rooms restores and maximizes Paltalk first, including reopening it from the tray when needed.
2. Enter the exact names exposed by the room tile buttons, in the desired order. For example: `XXX _ L_O_V_E _ _C_O_N_N_E_C_T_I_O_N _ XXX`. Leave unused entries blank.
3. Choose **Regular (3 rooms)** to open populated entries from Room 1–3, or **VIP (5 rooms)** to open populated entries from Room 1–5. Enable **Open when Paltalk starts** to run the selected room queue shortly after Paltalk starts; otherwise use **Open rooms** manually. Room names, delay, mode and automatic-opening choice are saved automatically.
4. The app first queues every visible matching tile, then invokes the queued rooms in order. This lets it continue after Paltalk changes away from the Rooms view when the first room opens. Check the activity log for each invocation. The **Open rooms** button changes to **Stop** while opening; click it to stop subsequent rooms. It cannot interrupt an invocation already in progress.

Reorder rooms by dragging the ⋮⋮ handle beside a name onto another room field, or by dragging selected room text onto another field. The room moves to that position and the new order is saved. Regular mode opens the first three positions; VIP mode includes all five.

While Paltalk's Rooms view and its Recently Visited section are visible, the app checks for rooms about every second and adds them to its saved history. It keeps previously collected rooms even when they no longer appear in Paltalk's current filter. Use **Recently visited** to view the saved list, then select a name and click **Copy selected name**, or double-click it, and paste it into a room field. Saved rooms remain available if the Paltalk list cannot be read.

Use the **Open** or **Close** button beside a room name to manage that room on its own. The button reflects the detected room state and the saved room name remains in the list. If the state is unavailable, **Open** restores Paltalk and checks whether the room is already open first. Opening still requires the tile to be visible in Paltalk's My Rooms / Rooms view. The activity log reports whether a control was invoked; an invocation does not independently verify the result.

**Other open rooms** shows detected rooms outside the active configured entries. In Regular mode, open rooms in positions 4–5 also appear there. Each row has a Close button and disappears after the room closes. The list is not saved. **Close all** restores and maximizes Paltalk, then checks and closes detected open rooms from both lists, regardless of the selected mode. Room detection requires Paltalk to be available; the last known list remains visible when a scan is unavailable.

The delay between rooms is at least five seconds to give rooms time to load. Previously saved delays below five seconds are raised to five seconds.

Room names and the delay are stored in `%LOCALAPPDATA%\PaltalkRoomOpener\room_names.json` (under the current user's profile). Before opening rooms, the app opens Paltalk's room browser and selects My Rooms. It searches for exactly named UI Automation buttons and invokes a matching button only when it is onscreen and has positive width. A successful invocation means the button was invoked; it does not independently verify that the room joined. If a room is not found, the app logs the failure and continues with the next room. Paltalk's layout and permissions may affect which tiles are visible.

## Camera Opener

Enter up to 200 exact usernames on the Camera Opener tab and add them to the list. Double-click an entry to edit it. Additions, edits and removals are saved and take effect during monitoring; newly added names are checked on the next scan. Start monitoring manually, or enable **Start when Paltalk starts**. A green dot marks a live camera detected in the visible room during monitoring; an unmarked name may simply be outside the visible scan. Enable **Prompt to add manually opened cameras** to be asked whether to add a newly opened camera username while monitoring. The visible room list must remain readable; cameras already open when monitoring or the option starts are not prompted. Monitoring can start with an empty list when this option is enabled. Camera settings are stored separately in `%LOCALAPPDATA%\PaltalkRoomOpener\camera_names.json`.

**Portrait adjustment** controls whether monitoring may move Paltalk to reveal camera buttons clipped on a portrait display. It is on by default, is saved with the camera settings, and can be changed while monitoring.

Display a room with its Mic Queue or On Cam heading and member rows visible and unobscured. The watcher uses Windows OCR to read both visible sections and UI Automation to invoke the camera button beside a matching name. It checks the row again before invoking and skips uncertain matches. After invoking, it checks a fresh scan for the green open-view icon and reports whether the state change was confirmed. It does not scroll or monitor rooms that are not displayed. OCR errors can prevent a match, particularly for similar letters; the log reports names it cannot find. The current Paltalk blue camera and green open-view icons are used to distinguish the states, so theme or interface changes can affect detection. The icon confirms the displayed control state, not the contents of the video. Stop monitoring before manually rearranging windows if the list cannot remain unobscured.

The watcher checks three OCR readings and attempts to remove colored badges beside names. One complete reading that exactly matches a saved username can open a camera even if the other readings differ. Rows matching multiple saved usernames and usernames matching multiple rows are skipped. OCR can misread a different person's name as a saved username, so an exact OCR match is not a guarantee of identity. When a name cannot be matched, the activity log includes the visible On Cam text and readings matched to camera buttons. These diagnostics can include other people’s usernames.

After invoking a camera, the watcher waits one second before opening another. Stop interrupts that wait and cancels an OCR process in progress.

The watcher waits a quarter of a second between scans. Each scan also takes time to read the visible list, so the actual interval varies. A camera that has already been attempted is not attempted again for at least two seconds.

## Admin Actions

Add banned phrases on the **Admin Actions** tab. Double-click a phrase or select it and click **Edit selected** to change it; select a phrase and click **Remove selected** to remove it and immediately save the list. Click **Save phrases** to keep additions and edits. The list is stored in `%LOCALAPPDATA%\PaltalkRoomOpener\admin_actions.json` and supports emoji. Empty and duplicate phrases are rejected.

With a room displayed in Paltalk, click **Start reading chat** to show readable messages and their senders in the log, then **Stop reading chat** to stop. It includes currently loaded messages and follows the selected room. In **Review mode**, new messages containing a saved phrase, matched without regard to case, appear in the match log for inspection; no users are bounced. Existing messages are ignored for matching when reading starts or the selected room changes. Saved phrase changes apply while the reader is running. The selected room is identified by its UI ID because its name is not exposed by the inspected controls. Messages with an uncertain sender are omitted. The reader polls, so messages that appear and disappear between readings may be missed.
