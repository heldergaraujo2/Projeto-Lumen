from __future__ import annotations

# Default Unreal Editor shortcuts documented by Epic.
OPEN_ASSET = ("CTRL", "P")
OPEN_LEVEL = ("CTRL", "O")
SAVE = ("CTRL", "S")
SAVE_ALL = ("CTRL", "SHIFT", "S")
PLAY_IN_EDITOR = ("ALT", "P")
STOP_PLAY = ("ESC",)

SUPPORTED_SHORTCUTS = {
    "open_asset": OPEN_ASSET,
    "open_level": OPEN_LEVEL,
    "save": SAVE,
    "save_all": SAVE_ALL,
    "play_in_editor": PLAY_IN_EDITOR,
    "stop_play": STOP_PLAY,
}
