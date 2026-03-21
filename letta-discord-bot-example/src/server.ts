import 'dotenv/config';
import express from 'express';
import { Client, GatewayIntentBits, Message, OmitPartialGroupDMChannel, Partials } from 'discord.js';
import { sendMessage, MessageType, splitMessage, cleanupUserBlocks, processStream } from './messages';

console.log('🚀 Starting Discord bot...');
console.log('📋 Environment check:');
console.log('  - DISCORD_TOKEN:', process.env.DISCORD_TOKEN ? '✓ Set' : '✗ Missing');
console.log('  - LETTA_API_KEY:', process.env.LETTA_API_KEY ? '✓ Set' : '✗ Missing');
console.log('  - LETTA_AGENT_ID:', process.env.LETTA_AGENT_ID ? '✓ Set' : '✗ Missing');
console.log('  - LETTA_BASE_URL:', process.env.LETTA_BASE_URL || 'http://localhost:8283 (default)');

const app = express();
const PORT = process.env.PORT || 3001;
const RESPOND_TO_DMS = process.env.RESPOND_TO_DMS === 'true';
const RESPOND_TO_MENTIONS = process.env.RESPOND_TO_MENTIONS === 'true';
const RESPOND_TO_BOTS = process.env.RESPOND_TO_BOTS === 'true';
const RESPOND_TO_GENERIC = process.env.RESPOND_TO_GENERIC === 'true';
const CHANNEL_ID = process.env.DISCORD_CHANNEL_ID;  // Optional: only listen in this channel
const RESPONSE_CHANNEL_ID = process.env.DISCORD_RESPONSE_CHANNEL_ID;  // Optional: only respond in this channel
const MESSAGE_REPLY_TRUNCATE_LENGTH = 100;  // how many chars to include
const MESSAGE_BATCH_ENABLED = process.env.MESSAGE_BATCH_ENABLED === 'true';
const MESSAGE_BATCH_SIZE = parseInt(process.env.MESSAGE_BATCH_SIZE || '10', 10);
const MESSAGE_BATCH_TIMEOUT_MS = parseInt(process.env.MESSAGE_BATCH_TIMEOUT_MS || '30000', 10);
const REPLY_IN_THREADS = process.env.REPLY_IN_THREADS === 'true';
const USER_BLOCKS_CLEANUP_INTERVAL_MINUTES = parseInt(process.env.USER_BLOCKS_CLEANUP_INTERVAL_MINUTES || '60', 10);
const ENABLE_THREAD_CONVERSATIONS = process.env.ENABLE_THREAD_CONVERSATIONS === 'true';
const THREAD_CONVERSATIONS_RESPOND_WITHOUT_MENTION = process.env.THREAD_CONVERSATIONS_RESPOND_WITHOUT_MENTION === 'true';
const HEARTBEAT_ENABLED = process.env.HEARTBEAT_ENABLED === 'true';
const HEARTBEAT_MIN_INTERVAL_MINUTES = parseInt(process.env.HEARTBEAT_MIN_INTERVAL_MINUTES || '20', 10);
const HEARTBEAT_MAX_INTERVAL_MINUTES = parseInt(process.env.HEARTBEAT_MAX_INTERVAL_MINUTES || '60', 10);

console.log('⚙️  Configuration:');
console.log('  - RESPOND_TO_DMS:', RESPOND_TO_DMS);
console.log('  - RESPOND_TO_MENTIONS:', RESPOND_TO_MENTIONS);
console.log('  - RESPOND_TO_GENERIC:', RESPOND_TO_GENERIC);
console.log('  - REPLY_IN_THREADS:', REPLY_IN_THREADS);
console.log('  - MESSAGE_BATCH_ENABLED:', MESSAGE_BATCH_ENABLED);

function truncateMessage(message: string, maxLength: number): string {
    if (message.length > maxLength) {
        return message.substring(0, maxLength - 3) + '...'; // Truncate and add ellipsis
    }
    return message;
}

console.log('🔧 Creating Discord client...');
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds, // Needed for commands and mentions
    GatewayIntentBits.GuildMessages, // Needed to read messages in servers
    GatewayIntentBits.MessageContent, // Required to read message content
    GatewayIntentBits.DirectMessages, // Needed to receive DMs
  ],
  partials: [Partials.Channel] // Required for handling DMs
});

// Handle process-level errors
process.on('unhandledRejection', (error) => {
  console.error('❌ Unhandled promise rejection:', error);
});

process.on('uncaughtException', (error) => {
  console.error('❌ Uncaught exception:', error);
  process.exit(1);
});

client.on('error', (error) => {
  console.error('🛑 Discord client error:', error);
});

// Discord Bot Ready Event
client.once('ready', async () => {
  console.log(`🤖 Logged in as ${client.user?.tag}!`);
  if (MESSAGE_BATCH_ENABLED) {
    console.log(`📦 Message batching enabled: ${MESSAGE_BATCH_SIZE} messages or ${MESSAGE_BATCH_TIMEOUT_MS}ms timeout`);
  }
  
  // Clean up any accumulated user blocks from previous sessions
  await cleanupUserBlocks();
  
  // Start periodic cleanup timer for user blocks
  if (USER_BLOCKS_CLEANUP_INTERVAL_MINUTES > 0) {
    const intervalMs = USER_BLOCKS_CLEANUP_INTERVAL_MINUTES * 60 * 1000;
    console.log(`🧹 User blocks cleanup scheduled every ${USER_BLOCKS_CLEANUP_INTERVAL_MINUTES} minutes`);
    setInterval(async () => {
      console.log(`🧹 Running scheduled user blocks cleanup...`);
      await cleanupUserBlocks();
    }, intervalMs);
  }
});

// Message batching infrastructure
interface BatchedMessage {
  message: OmitPartialGroupDMChannel<Message<boolean>>;
  messageType: MessageType;
  timestamp: number;
}

const channelMessageBuffers = new Map<string, BatchedMessage[]>();
const channelBatchTimers = new Map<string, NodeJS.Timeout>();

async function drainMessageBatch(channelId: string) {
  const buffer = channelMessageBuffers.get(channelId);
  const timer = channelBatchTimers.get(channelId);

  if (timer) {
    clearTimeout(timer);
    channelBatchTimers.delete(channelId);
  }

  if (!buffer || buffer.length === 0) {
    return;
  }

  console.log(`📦 Draining batch for channel ${channelId}: ${buffer.length} messages`);

  // Get the last message to use as the reply target
  const lastMessage = buffer[buffer.length - 1].message;
  const canRespond = shouldRespondInChannel(lastMessage);

  // Format all messages in batch
  const batchedContent = buffer.map((bm, idx) => {
    const { message, messageType } = bm;
    const username = message.author.username;
    const userId = message.author.id;
    const content = message.content;
    const timestamp = message.createdAt.toISOString();

    let prefix = '';
    if (messageType === MessageType.MENTION) {
      prefix = `[${timestamp}] [${username} (id=${userId}) mentioned you]`;
    } else if (messageType === MessageType.REPLY) {
      prefix = `[${timestamp}] [${username} (id=${userId}) replied to you]`;
    } else if (messageType === MessageType.DM) {
      prefix = `[${timestamp}] [${username} (id=${userId}) sent you a DM]`;
    } else {
      prefix = `[${timestamp}] [${username} (id=${userId})]`;
    }

    return `${idx + 1}. ${prefix} ${content}`;
  }).join('\n');

  const channelName = 'name' in lastMessage.channel && lastMessage.channel.name
    ? `#${lastMessage.channel.name}`
    : `channel ${channelId}`;

  const batchMessage = `[Batch of ${buffer.length} messages from ${channelName}]\n${batchedContent}`;

  console.log(`📦 Batch content:\n${batchMessage}`);

  try {
    // Send batch to agent using the last message as context
    const msg = await sendMessage(lastMessage, buffer[buffer.length - 1].messageType, canRespond, batchMessage);

    if (msg !== "" && canRespond) {
      await sendSplitReply(lastMessage, msg);
      console.log(`📦 Batch response sent (${msg.length} chars)`);
    } else if (msg !== "" && !canRespond) {
      console.log(`📦 Agent generated response but not responding (not in response channel): ${msg}`);
    }
  } catch (error) {
    console.error("🛑 Error processing batch:", error);
  }

  // Clear the buffer
  channelMessageBuffers.delete(channelId);
}

function addMessageToBatch(message: OmitPartialGroupDMChannel<Message<boolean>>, messageType: MessageType) {
  const channelId = message.channel.id;

  if (!channelMessageBuffers.has(channelId)) {
    channelMessageBuffers.set(channelId, []);
  }

  const buffer = channelMessageBuffers.get(channelId)!;
  buffer.push({
    message,
    messageType,
    timestamp: Date.now()
  });

  console.log(`📦 Added message to batch (${buffer.length}/${MESSAGE_BATCH_SIZE})`);

  // Check if we should drain due to size
  if (buffer.length >= MESSAGE_BATCH_SIZE) {
    console.log(`📦 Batch size limit reached, draining...`);
    drainMessageBatch(channelId);
    return;
  }

  // Set/reset the timeout
  if (channelBatchTimers.has(channelId)) {
    clearTimeout(channelBatchTimers.get(channelId)!);
  }

  const timeout = setTimeout(() => {
    console.log(`📦 Batch timeout reached, draining...`);
    drainMessageBatch(channelId);
  }, MESSAGE_BATCH_TIMEOUT_MS);

  channelBatchTimers.set(channelId, timeout);
}

// Helper function to check if bot should respond in this channel
function shouldRespondInChannel(message: OmitPartialGroupDMChannel<Message<boolean>>): boolean {
  // If RESPONSE_CHANNEL_ID is not set, respond everywhere
  if (!RESPONSE_CHANNEL_ID) {
    return true;
  }
  
  // For threads, check the parent channel ID
  const channelId = message.channel.isThread() 
    ? message.channel.parentId 
    : message.channel.id;
    
  // If RESPONSE_CHANNEL_ID is set, only respond in that channel
  return channelId === RESPONSE_CHANNEL_ID;
}

// Helper function to send a message, splitting if necessary
async function sendSplitReply(message: OmitPartialGroupDMChannel<Message<boolean>>, content: string) {
  const chunks = splitMessage(content);
  
  if (REPLY_IN_THREADS && message.guild !== null) {
    let thread;
    
    if (message.channel.isThread()) {
      thread = message.channel;
    } else if (message.hasThread && message.thread) {
      thread = message.thread;
    } else {
      const threadName = message.cleanContent.substring(0, 50) || 'Chat';
      thread = await message.startThread({ name: threadName });
    }
    
    if (thread) {
      for (const chunk of chunks) {
        await thread.send(chunk);
      }
    }
  } else {
    for (let i = 0; i < chunks.length; i++) {
      if (i === 0) {
        await message.reply(chunks[i]);
      } else {
        await message.channel.send(chunks[i]);
      }
    }
  }
}

// Helper function to send a message to a channel, splitting if necessary
async function sendSplitMessage(channel: { send: (content: string) => Promise<any> }, content: string) {
  const chunks = splitMessage(content);
  for (const chunk of chunks) {
    await channel.send(chunk);
  }
}

// Helper function to send a message and receive a response
async function processAndSendMessage(message: OmitPartialGroupDMChannel<Message<boolean>>, messageType: MessageType) {
  // If batching is enabled, add to batch instead of processing immediately
  if (MESSAGE_BATCH_ENABLED) {
    addMessageToBatch(message, messageType);
    return;
  }

  // Otherwise, process immediately (original behavior)
  try {
    const canRespond = shouldRespondInChannel(message);
    const msg = await sendMessage(message, messageType, canRespond);
    if (msg !== "" && canRespond) {
      await sendSplitReply(message, msg);
      console.log(`Message sent (${msg.length} chars)`);
    } else if (msg !== "" && !canRespond) {
      console.log(`Agent generated response but not responding (not in response channel): ${msg}`);
    }
  } catch (error) {
    console.error("🛑 Error processing and sending message:", error);
  }
}


// Reflective heartbeat — periodically sends a check-in message to the PA
// so it can be proactive with full conversation context.
async function startHeartbeat() {
  if (!HEARTBEAT_ENABLED) {
    console.log("💓 Heartbeat disabled (HEARTBEAT_ENABLED not set to true).");
    return;
  }

  const AGENT_ID = process.env.LETTA_AGENT_ID;
  if (!AGENT_ID) {
    console.log("💓 Heartbeat disabled (LETTA_AGENT_ID not set).");
    return;
  }

  console.log(`💓 Heartbeat started (interval: ${HEARTBEAT_MIN_INTERVAL_MINUTES}-${HEARTBEAT_MAX_INTERVAL_MINUTES} minutes)`);

  const scheduleNextHeartbeat = () => {
    const minMs = HEARTBEAT_MIN_INTERVAL_MINUTES * 60 * 1000;
    const maxMs = HEARTBEAT_MAX_INTERVAL_MINUTES * 60 * 1000;
    const intervalMs = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
    const intervalMin = (intervalMs / 60000).toFixed(1);

    console.log(`💓 Next heartbeat in ${intervalMin} minutes`);

    setTimeout(async () => {
      try {
        // Get the channel to deliver any proactive messages
        let channel: { send: (content: string) => Promise<any> } | undefined = undefined;
        if (CHANNEL_ID) {
          try {
            const fetchedChannel = await client.channels.fetch(CHANNEL_ID);
            if (fetchedChannel && 'send' in fetchedChannel) {
              channel = fetchedChannel as any;
            }
          } catch (error) {
            console.error("💓 Error fetching channel:", error);
          }
        }

        const Letta = (await import('@letta-ai/letta-client')).default;
        const lettaClient = new Letta({
          apiKey: process.env.LETTA_API_KEY || 'your_letta_api_key',
          baseURL: process.env.LETTA_BASE_URL || 'http://localhost:8283',
        });

        const heartbeatMessage = {
          role: "user" as const,
          content:
            '[HEARTBEAT] This is a scheduled check-in.\n' +
            'First, search your archival memory for "[monitoring:task:" to find active monitoring tasks. ' +
            'For each task found, parse the JSON and delegate to the appropriate worker.\n' +
            'Then, review your TODO block. If there are actionable items, pick one and work on it.\n' +
            'If there are no monitoring tasks and the TODO block is empty, stay silent.'
        };

        console.log(`💓 Sending heartbeat to PA (agent=${AGENT_ID})`);
        const response = await lettaClient.agents.messages.create(AGENT_ID, {
          messages: [heartbeatMessage],
          streaming: true,
          background: true,
        });

        if (response) {
          await processStream(response, channel);
          console.log('💓 Heartbeat complete.');
        }
      } catch (error) {
        console.error('💓 Error during heartbeat:', error);
      }

      // Schedule the next heartbeat
      scheduleNextHeartbeat();
    }, intervalMs);
  };

  // Start the first heartbeat cycle
  scheduleNextHeartbeat();
}

// Handle messages mentioning the bot
client.on('messageCreate', async (message) => {
  if (CHANNEL_ID && message.channel.id !== CHANNEL_ID) {
    // Ignore messages from other channels
    console.log(`📩 Ignoring message from other channels (only listening on channel=${CHANNEL_ID})...`);
    return;
  }

  if (message.author.id === client.user?.id) {
    // Ignore messages from the bot itself
    console.log(`📩 Ignoring message from myself...`);
    return;
  }

  if (message.author.bot && !RESPOND_TO_BOTS) {
    // Ignore other bots
    console.log(`📩 Ignoring other bot...`);
    return;
  }

  // Ignore messages that start with !
  if (message.content.startsWith('!')) {
    console.log(`📩 Ignoring message that starts with !...`);
    return;
  }

  // 📨 Handle Direct Messages (DMs)
  if (message.guild === null) { // If no guild, it's a DM
    console.log(`📩 Received DM from ${message.author.username}: ${message.content}`);
    if (RESPOND_TO_DMS) {
      processAndSendMessage(message, MessageType.DM);
    } else {
      console.log(`📩 Ignoring DM...`);
    }
    return;
  }

  // Thread conversations: handle ALL messages in thread uniformly (before mention/reply checks)
  // This ensures consistent batching behavior for all messages in the same thread
  if (ENABLE_THREAD_CONVERSATIONS && 
      THREAD_CONVERSATIONS_RESPOND_WITHOUT_MENTION && 
      message.channel.isThread()) {
    
    // Still detect message type for appropriate prefix to agent
    let messageType = MessageType.GENERIC;
    const isMentionInThread = message.mentions.has(client.user || '');
    
    if (isMentionInThread) {
      messageType = MessageType.MENTION;
    } else if (message.reference?.messageId) {
      // Check if replying to bot's message
      try {
        const repliedTo = await message.channel.messages.fetch(message.reference.messageId);
        if (repliedTo.author.id === client.user?.id) {
          messageType = MessageType.REPLY;
        }
      } catch (error) {
        // Ignore fetch errors, just use GENERIC
      }
    }
    
    console.log(`📩 Thread conversation (${messageType}) from ${message.author.username}: ${message.content}`);
    processAndSendMessage(message, messageType);
    return;
  }

  // Check if the bot is mentioned or if the message is a reply to the bot
  const isMention = message.mentions.has(client.user || '');
  let isReplyToBot = false;
  
  // If it's a reply, check if it's to the bot
  if (message.reference && message.reference.messageId) {
    try {
      const originalMessage = await message.channel.messages.fetch(message.reference.messageId);
      isReplyToBot = originalMessage.author.id === client.user?.id;
    } catch (error) {
      console.log(`⚠️ Could not fetch referenced message: ${error instanceof Error ? error.message : error}`);
    }
  }
  
  if (RESPOND_TO_MENTIONS && (isMention || isReplyToBot)) {
    console.log(`📩 Received message from ${message.author.username}: ${message.content}`);

    // Check if we can respond in this channel before showing typing indicator
    const canRespond = shouldRespondInChannel(message);
    console.log(`💬 Can respond in this channel: ${canRespond} (channel=${message.channel.id}, responseChannel=${RESPONSE_CHANNEL_ID || 'any'})`);
    if (canRespond) {
      console.log(`⌨️  Sending typing indicator...`);
      if (REPLY_IN_THREADS && message.guild !== null) {
        if (message.channel.isThread()) {
          await message.channel.sendTyping();
        } else if (message.hasThread) {
          await message.thread!.sendTyping();
        } else {
          await message.channel.sendTyping();
        }
      } else {
        await message.channel.sendTyping();
      }
    } else {
      console.log(`⌨️  Skipping typing indicator (observation-only channel)`);
    }

    let msgContent = message.content;
    let messageType = MessageType.MENTION; // Default to mention

    // If it's a reply to the bot, update message type and content
    if (isReplyToBot && message.reference && message.reference.messageId) {
      try {
        const originalMessage = await message.channel.messages.fetch(message.reference.messageId);
        messageType = MessageType.REPLY;
        msgContent = `[Replying to previous message: "${truncateMessage(originalMessage.content, MESSAGE_REPLY_TRUNCATE_LENGTH)}"] ${msgContent}`;
      } catch (error) {
        console.log(`⚠️ Could not fetch referenced message content: ${error instanceof Error ? error.message : error}`);
      }
    }

    // If batching is enabled, add to batch instead of processing immediately
    if (MESSAGE_BATCH_ENABLED) {
      addMessageToBatch(message, messageType);
      return;
    }

    // Otherwise, process immediately (original behavior)
    const msg = await sendMessage(message, messageType, canRespond);
    if (msg !== "" && canRespond) {
      await sendSplitReply(message, msg);
    } else if (msg !== "" && !canRespond) {
      console.log(`Agent generated response but not responding (not in response channel): ${msg}`);
    }
    return;
  }

  // Catch-all, generic non-mention message
  if (RESPOND_TO_GENERIC) {
    console.log(`📩 Received (non-mention) message from ${message.author.username}: ${message.content}`);
    processAndSendMessage(message, MessageType.GENERIC);
    return;
  }
});

// Start the Discord bot
console.log(`🌐 Starting Express server on port ${PORT}...`);
app.listen(PORT, async () => {
  console.log(`✅ Express server listening on port ${PORT}`);
  
  if (!process.env.DISCORD_TOKEN) {
    console.error('❌ DISCORD_TOKEN not set! Cannot login to Discord.');
    process.exit(1);
  }
  
  try {
    console.log('🔐 Attempting Discord login...');
    await client.login(process.env.DISCORD_TOKEN);
    console.log('✅ Discord login successful');
    startHeartbeat();
  } catch (error) {
    console.error('❌ Discord login failed:', error);
    process.exit(1);
  }
});