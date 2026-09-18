# MysticForge (Early Alpha)

**A ROM editor for Final Fantasy Mystic Quest (SNES)**  
*Current Version: 0.2 (September 18, 2026)*

> **Warning:** This is an early alpha release. Use at your own risk! Not everything is complete, and some features are currently read-only. Always keep backups of your ROM and save files.

<p align="center">
  <img width="908" height="703" alt="MysticForge Preview" src="https://github.com/user-attachments/assets/506db728-769a-4cbb-b1b6-ee6ede5d339c" />
</p>

---

## Compatibility

* **Target ROM:** USA 1.0 release.
* **Life Spell Bug:** Includes an optional built-in patch/fix for the v1.0 Life spell targeting bug.
* **Future Plans:** I will look into adding v1.1 support later on.

---

## Latest Updates

### Sept 18, 2026
* **Events & Scripts:** Added a bunch of event editing tools. You can now create new NPCs, assign them custom dialogue, or write an entire event sequence. Actions are currently limited, but the basics are there.
* **General:** Various additions and bug fixes throughout. Just play around with it to see what's new. Make sure to back up your files first!

---

## Current Status & Known Issues

* **Known Issue:** New overworld locations cannot be named yet. They seem to pull their names from the map's size template (needs more research).
* **Scripting/Events:** Event and script editing is partially implemented; basic editing works, but advanced actions are still in progress.
* **Testing:** I've tested everything I could, but I haven't completed a full playthrough to verify every edge case. Expect bugs or potential game-breaking issues.
* **UI/Labels:** Some labels, menus, or terms might be named oddly. I plan on doing a pass soon to clean up the wording and interface.

---

## Screenshots

<table>
  <tr>
    <td width="50%"><img width="908" height="703" alt="Interface preview 1" src="https://github.com/user-attachments/assets/9de2fb02-fd87-4a11-b4f0-0168cda2d5b1" /></td>
    <td width="50%"><img width="908" height="703" alt="Interface preview 2" src="https://github.com/user-attachments/assets/137426fb-6093-4a18-b3d7-c52b57d7b23a" /></td>
  </tr>
  <tr>
    <td width="50%"><img width="908" height="703" alt="Interface preview 3" src="https://github.com/user-attachments/assets/c795abd0-185c-48ff-8226-432642c0c2df" /></td>
    <td width="50%"><img width="1002" height="703" alt="Interface preview 4" src="https://github.com/user-attachments/assets/b1223955-467a-45a5-8635-33f95cd3a8ce" /></td>
  </tr>
  <tr>
    <td width="50%"><img width="658" height="495" alt="Interface preview 5" src="https://github.com/user-attachments/assets/0c5ad72e-3067-4bb2-8d79-925c2e63a355" /></td>
    <td width="50%"><img width="1280" height="775" alt="Interface preview 6" src="https://github.com/user-attachments/assets/75b540a3-5859-4d40-ba16-1c45494067c1" /></td>
  </tr>
</table>

---

## Development Notes

I know some people have mixed feelings about it, but AI was used to assist in the development of this software. Without it, this tool wouldn't exist. I’ve always been surprised by the lack of tools for Mystic Quest, and AI has become pretty great at SNES assembly, reverse engineering, and comparing code directly against the ROM. Sure, I could have tackled it manually, but work and life mean that would have taken months or years.

---

## Credits & Thanks

* [FFMQRando](https://github.com/wildham0/FFMQRando/) – Great project, used parts of their documentation and findings during development.
* [ffmq-info](https://github.com/TheAnsarya/ffmq-info) – Helped a ton, especially the disassembled assembly code (although there were discrepancies against the clean 1.0 ROM, but those were sorted out).

---

## License / Disclaimer

No formal license provided—treat this as public domain / do whatever you want with it. Modify it, fork it, sell it, or claim it as your own; I really don't care lol. 

Just don't blame me if it corrupts your ROM or breaks your save. I'll do my best to push fixes and update the editor as time allows, but no guarantees!
