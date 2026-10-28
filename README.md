# Paltalk Room Opener

A Windows desktop app that invokes up to five named Paltalk room tiles in order.

`main.py` is the main entry point. Application code is organized in `paltalk_room_opener/` by responsibility: UI window, settings, worker thread, Windows UI Automation, and styling.

## Setup

Install the 64-bit CPython 3.14 release, then in PowerShell from this folder run:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe" -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

The 3.14 interpreter is required because this project depends on binary packages for Qt, image capture, process inspection, and .NET UI Automation. The specified package versions ship Python 3.14-compatible Windows wheels. If `main.py` is launched with a different Python that lacks `pythonnet`, it will use the project's `.venv` automatically when that environment exists.

The selected tab is restored on startup and stored in `%APPDATA%\PaltalkRoomOpener\app_state.json`.

## Use

Closing the window keeps the app running in the Windows notification area, including any active monitoring. Click the tray icon or choose **Open Paltalk Automation** from its menu to restore the window. Choose **Quit** from the tray menu to stop background work and exit. If the system tray is unavailable, closing the window exits normally.

1. Start Paltalk and display the My Rooms / Rooms view containing the room tiles. Keep the relevant tiles visible and Paltalk available while the app runs.
2. Enter the exact names exposed by the room tile buttons, in the desired order. For example: `XXX _ L_O_V_E _ _C_O_N_N_E_C_T_I_O_N _ XXX`. Leave unused entries blank.
3. Choose **Regular (3 rooms)** to open populated entries from Room 1–3, or **VIP (5 rooms)** to open populated entries from Room 1–5. Enable **Open when Paltalk starts** to run the selected room queue shortly after Paltalk starts; otherwise use **Open rooms** manually. Settings, including the selected mode and automatic-opening choice, are saved automatically and can also be saved using **Save settings**.
4. The app first queues every visible matching tile, then invokes the queued rooms in order. This lets it continue after Paltalk changes away from the Rooms view when the first room opens. Check the activity log for each invocation. The **Open rooms** button changes to **Stop** while opening; click it to stop subsequent rooms. It cannot interrupt an invocation already in progress.

Reorder rooms by dragging the ⋮⋮ handle beside a name onto another room field, or by dragging selected room text onto another field. The room moves to that position and the new order is saved. Regular mode opens the first three positions; VIP mode includes all five.

Use **Recently visited** while Paltalk's Rooms view is open to collect rooms from its Recently Visited section. Each refresh adds new names to a saved history, keeping previously collected rooms even when they no longer appear in Paltalk's current filter. Select a name and click **Copy selected name**, or double-click it, then paste it into a room field. Saved rooms remain available if the Paltalk list cannot be read.

Use the **Open** or **Close** button beside a room name to manage that room on its own. The button reflects the detected room state and the saved room name remains in the list. Opening still requires the tile to be visible in Paltalk's My Rooms / Rooms view. The activity log reports whether a control was invoked; an invocation does not independently verify the result.

**Close all** closes all detected open rooms named in the five configured entries, regardless of the selected mode. Rooms not listed in the app are not included.

The delay between rooms is at least five seconds to give rooms time to load. Previously saved delays below five seconds are raised to five seconds.

Room names and the delay are stored in `%APPDATA%\PaltalkRoomOpener\room_names.json` (under the current user's profile). The app finds Paltalk windows by process name, searches for exactly named UI Automation buttons, and invokes a matching button only when it is onscreen and has positive width. A successful invocation means the button was invoked; it does not independently verify that the room joined. If a room is not found, the app logs the failure and continues with the next room. Paltalk's layout, permissions, and navigation may affect which tiles are visible; return to the Rooms view if necessary.

## Camera Opener

Enter up to 200 exact usernames on the Camera Opener tab, add them to the list, and save. Double-click an entry to edit it. Start monitoring manually, or enable **Start when Paltalk starts**. Camera settings are stored separately in `%APPDATA%\PaltalkRoomOpener\camera_names.json`; edits take effect when monitoring is next started.

Display a room with its Mic Queue or On Cam heading and member rows visible and unobscured. The watcher uses Windows OCR to read both visible sections and UI Automation to invoke the camera button beside a matching name. It checks the row again before invoking and skips uncertain matches. It does not scroll or monitor rooms that are not displayed. OCR errors can prevent a match, particularly for similar letters; the log reports names it cannot find. The current Paltalk blue camera and green open-view icons are used to distinguish the states, so theme or interface changes can affect detection. An invocation does not itself confirm that the video opened. Stop monitoring before manually rearranging windows if the list cannot remain unobscured.

The watcher checks three OCR readings and attempts to remove colored badges beside names. One complete reading that exactly matches a saved username can open a camera even if the other readings differ. Rows matching multiple saved usernames and usernames matching multiple rows are skipped. OCR can misread a different person's name as a saved username, so an exact OCR match is not a guarantee of identity. When a name cannot be matched, the activity log includes the visible On Cam text and readings matched to camera buttons. These diagnostics can include other people’s usernames.

After invoking a camera, the watcher waits one second before opening another. Stop interrupts that wait and cancels an OCR process in progress.

## Admin Actions

Add banned phrases on the **Admin Actions** tab. Double-click a phrase or select it and click **Edit selected** to change it; select a phrase and click **Remove selected** to remove it and immediately save the list. Click **Save phrases** to keep additions and edits. The list is stored in `%APPDATA%\PaltalkRoomOpener\admin_actions.json` and supports emoji. Empty and duplicate phrases are rejected.

With a room displayed in Paltalk, click **Start reading chat** to show readable messages and their senders in the log, then **Stop reading chat** to stop. It includes currently loaded messages and follows the selected room. In **Review mode**, new messages containing a saved phrase, matched without regard to case, appear in the match log for inspection; no users are bounced. Existing messages are ignored for matching when reading starts or the selected room changes. Saved phrase changes apply while the reader is running. The selected room is identified by its UI ID because its name is not exposed by the inspected controls. Messages with an uncertain sender are omitted. The reader polls, so messages that appear and disappear between readings may be missed.
