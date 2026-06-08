# Sound assets

The current MVP uses browser speech synthesis for short English poker action announcements and Web Audio API synthesized fallback effects in `app/static/js/room.js`, so the game does not require external or copyrighted audio files.

If you want to replace the synthesized sounds later, add local audio files here using these event names:

- `deal`
- `check`
- `call`
- `bet`
- `raise`
- `all_in`
- `fold`
- `win`
- `showdown`
- `message`

Keep assets short, local, and royalty-free.
