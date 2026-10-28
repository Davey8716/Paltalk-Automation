## **Paltalk Buttons**



**All rooms tab**



Each room has its own three-dot Show Options button.



Paltalk gives each one a different generated BaseButton ID, for example:

\- One room: BaseButton7034

\- The Garage: BaseButton7073

So we should find a room by its name first, then select the Show Options button beside that specific room. We should not rely on one saved BaseButton number because it changes from room to room.



Recorded: ContactList\_ShopButton = Shop navigation button.



settings button = cog settings

Recorded: BaseButton15 = maximize/restore window.

Recorded: BaseButton14 = restore down. It replaces BaseButton15 when Paltalk is maximized.

BaseButton12 → minimize to system tray

BaseButton13 → minimize window

base button 11 = main app burger icon

Recorded: BaseButton80 opens the Virtual Gift Credits commerce page

Recorded: BaseButton82 = Rooms I Own toggle; it hides/shows your personal room.

Recorded: BaseButton125 = Rooms I Admin toggle.

Recorded: BaseButton127 = Rooms I Follow toggle.

Recorded: BaseButton133 = Recently Visited toggle.



Recorded: Browse Chat Rooms (BaseButton7450) focuses the Search Rooms text field and places the caret there.



**Opened room controls**



Area	Exposed control

Room header	Follow checkbox (Room\_Top\_FollowButton)

Room header	Room\_Top\_ShareButton, Room\_Top\_OwnerName, and Menu button (Room\_Top\_MenuButton)

Audio	Toggle Speaker and Show Speaker Menu

Webcam	Toggle Webcam and Show Webcam Menu

Video area	View All Videos, Open Settings, and Hide Video Area

Microphone	Lock Mic, Show Mic Menu, and Join Queue to Talk

Room chat	Send message edit control, Send Emoji/Sticker, and Send Gift (edit widget)



Recorded: Toggle Webcam in Room\_Top\_WebcamButton toggles your webcam. Its current generated ID is BaseButton12428; locate it by name and parent rather than relying on that number.



There’s a second Toggle Webcam button in the video area that we haven’t tested yet.



**Camera Automation**



**I invoked the room header’s Toggle Webcam button successfully:**

**- Current ID: BaseButton12428**

**- Parent: Room\_Top\_WebcamButton**

**- UI Automation pattern: InvokePattern**

**The accessibility label remained Toggle Webcam afterward, and no confirmation dialog appeared. That doesn’t tell us whether the camera actually started or stopped, so please check the webcam indicator or video preview before recording its resulting state.**



**There’s also a separate Toggle Webcam button in the video area (BaseButton12454); I tested the one in the room header.**



**The first button toggle my webcam**



**Recorded: Show Webcam Menu opens the Select a Camera menu. Its current generated ID is BaseButton13143, under Room\_Top\_WebcamButton.**



\- Camera buttons are exposed inside member rows as generated BaseButton IDs.

\- Clicking them opened the corresponding members’ cameras.

\- A user can appear in both Talking Now and On Cam.

\- Your camera button stayed BaseButton13026 after turning your webcam off and on, but changed to BaseButton13190 after restarting the room.

\- Don’t rely on a saved ID across room restarts. We still need a reliable way to associate each button with a username.



&#x20;

**Other Buttons**



Recorded: Subscription Button = Subscription button.

Recorded: Search Button = Search button.

Recorded: Add Pals Button = Add a Pal button.

Recorded: MyUserFull\_Status\_StatusButton = status changer dropdown.

Recorded: ContactList\_HomeButton = My Dashboard.

Recorded: ContactList\_LeaderboardButton = Paltalk Leaderboard.

Recorded: ContactList\_RewardsButton = Your Rewards dashboard.

Recorded: ContactListWidget\_Item\_Dave8787 = opens your own direct-message conversation.

Recorded: Send Image opens the Shop.

Recorded: Send Emoji/Sticker opens the emoji/sticker sub-window.

Recorded: BaseButton46 = image sender. Opens win 11 pathing to images.

Recorded: More Option = individual private-message burger/menu.

Recorded: Send Gift opens the Shop beside the message entry bar.

Paltalk also has another nearby shop-looking icon, but its UI Automation label does not accurately reflect that visual control.

Understood. I’ll skip Call and treat it as an outbound phone-call action.

Recorded: Send message edit control = focuses the current private-message text field.





Paltalk room opening via Windows UI Automation



1\. Query the Paltalk desktop window by its process ID.



2\. Search its descendant controls for a UI Automation element with:

&#x20;  - ControlType: Button

&#x20;  - Name: XXX \_ L\_O\_V\_E \_ \_C\_O\_N\_N\_E\_C\_T\_I\_O\_N \_ XXX



3\. Paltalk exposed three matching room-tile buttons. Select the visible one:

&#x20;  - IsOffscreen = false

&#x20;  - BoundingRectangle.Width > 0



4\. Invoke the button using UI Automation’s InvokePattern:

&#x20;  element.GetCurrentPattern(InvokePattern.Pattern).Invoke()



Result:

When the room was closed, invoking the visible named room-tile button opened the room directly from the My Rooms / Rooms view.



Important distinction:

The room’s left-panel entry used RoomItemWidget / ClickableLabel controls. Although they exposed InvokePattern, invoking them did not cause a visible action. The functional control was the named Button inside:

ROOM\_BROWSER\_WIDGET → RoomsView → RoomsTableView → RoomTiles

