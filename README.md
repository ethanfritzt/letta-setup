# Letta Setup

Docker setup for Letta server with a Discord bot and multi-agent system.

## Setup

1. Copy env template and add your API keys:
   ```
   cp env.template .env
   ```

2. Start the services:
   ```
   docker compose up -d
   ```

3. Create the agents:
   ```
   python -m agents.create_all
   ```

4. Add the Personal Assistant ID to your `.env` as `LETTA_AGENT_ID`

5. Restart the Discord bot:
   ```
   docker compose restart discord-bot
   ```
