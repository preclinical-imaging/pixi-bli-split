# PIXI BLI Split
This project includes a python library for splitting multi-subject bioluminescent imaging sessions into single subject sessions.

## Instructions

The PIXI plugin is required for running this within XNAT.

1. Build the image

    `docker build -t xnat/bli-split:1.0 .`
2. Add `xnat/command.json` to XNAT
3. Enable the command at the site and project level
4. Run the container 

