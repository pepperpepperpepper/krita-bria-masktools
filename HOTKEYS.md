# Hotkey Configuration for Bria Mask Tools

This plugin supports keyboard shortcuts for quick access to all features.

## Script Menu

In **Tools → Scripts**, you'll find:
- **Bria Mask Tools** - Toggle the docker visibility

## Hotkey Actions

The following actions can be assigned hotkeys in Krita (they won't appear in menus):

1. **Bria: Remove Background** - Instantly remove background from selected layer
2. **Bria: Remove Background with Mask** - Remove background using current mask/selection
3. **Bria: Generate Masks** - Generate AI masks for objects in the layer

## Settings Menu

In **Settings**, you'll find:
- **Configure BriaAI Plugin** - Open API key configuration dialog

## How to Set Up Hotkeys

1. Go to **Settings → Configure Krita → Keyboard Shortcuts**
2. In the search box, type "Bria"
3. You'll see all available Bria MaskTools actions
4. Click on an action and press your desired key combination
5. Click "OK" to save

## Suggested Hotkeys

Here are some suggested keyboard shortcuts (you can use any keys you prefer):

- **Remove Background**: `Ctrl+Alt+B`
- **Remove with Mask**: `Ctrl+Alt+M`
- **Generate Masks**: `Ctrl+Alt+G`
- **Toggle Batch**: `Ctrl+Alt+Shift+B`
- **Settings**: `Ctrl+Alt+S`

## Usage Tips

1. **Quick Workflow**: Assign hotkeys to your most used modes for rapid processing
2. **Batch Toggle**: Use the batch toggle hotkey before your mode hotkey to quickly process multiple layers
3. **Docker Required**: The docker must be open for hotkeys to work (except Settings)

## Notes

- Hotkeys execute immediately with current settings
- Make sure your API key is configured before using hotkeys
- If the docker isn't open, you'll get a reminder message
- Hotkeys respect the current batch mode setting