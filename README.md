# GithubCodeBot

Based on [SeanJxie/GithubCodeBot](https://github.com/SeanJxie/GithubCodeBot/tree/main)

Changes:
---
- Removed EXE setup
- Transitioned configuration to environment variables
- Now using `python-dotenv` instead of prompting user for config setup
- Grant permissions to access private repositories
- User can now specify lines to be printed
- Migrated to `discord.py v2.0`