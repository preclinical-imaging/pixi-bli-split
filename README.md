# PIXI BLI Split
This project includes a python library for splitting multi-subject bioluminescent imaging sessions into single subject sessions.

## Instructions

The PIXI plugin is required for running this within XNAT.

1. Build the image: `docker build -t xnat/bli-split:1.0 .`
2. Add `xnat/command_auto.json` to XNAT
3. Add `xnat/command_manual.json` to XNAT
4. Enable the command at the site and project level
5. Run the container in XNAT from a pixi:bliSessionData instance.