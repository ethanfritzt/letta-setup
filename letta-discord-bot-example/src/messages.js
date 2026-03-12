"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MessageType = void 0;
exports.sendMessage = sendMessage;
exports.sendTimerMessage = sendTimerMessage;
const letta_client_1 = require("@letta-ai/letta-client");
// If the token is not set, just use a dummy value
const client = new letta_client_1.LettaClient({
    token: process.env.LETTA_API_KEY || 'your_letta_api_key',
    baseUrl: process.env.LETTA_BASE_URL || 'https://api.letta.com',
});
const AGENT_ID = process.env.LETTA_AGENT_ID;
const USE_SENDER_PREFIX = process.env.LETTA_USE_SENDER_PREFIX === 'true';
const SURFACE_ERRORS = process.env.SURFACE_ERRORS === 'true';
var MessageType;
(function (MessageType) {
    MessageType["DM"] = "DM";
    MessageType["MENTION"] = "MENTION";
    MessageType["REPLY"] = "REPLY";
    MessageType["GENERIC"] = "GENERIC";
})(MessageType || (exports.MessageType = MessageType = {}));
// Helper function to process stream
const processStream = async (response, discordTarget) => {
    let agentMessageResponse = '';
    const sendAsyncMessage = async (content) => {
        if (discordTarget && content.trim()) {
            try {
                if ('reply' in discordTarget) {
                    await discordTarget.channel.send(content);
                }
                else {
                    await discordTarget.send(content);
                }
            }
            catch (error) {
                console.error('❌ Error sending async message:', error);
            }
        }
    };
    try {
        for await (const chunk of response) {
            // Handle different message types that might be returned
            if ('messageType' in chunk) {
                switch (chunk.messageType) {
                    case 'assistant_message':
                        if ('content' in chunk && typeof chunk.content === 'string') {
                            agentMessageResponse += chunk.content;
                        }
                        break;
                    case 'stop_reason':
                        console.log('🛑 Stream stopped:', chunk);
                        break;
                    case 'reasoning_message':
                        console.log('🧠 Reasoning:', chunk);
                        if ('content' in chunk && typeof chunk.content === 'string') {
                            await sendAsyncMessage(`**Reasoning**\n> ${chunk.content}`);
                        }
                        break;
                    case 'tool_call_message':
                        console.log('🔧 Tool call:', chunk);
                        if ('name' in chunk && typeof chunk.name === 'string') {
                            let toolMessage = `**Tool Call (${chunk.name})**`;
                            if ('arguments' in chunk && chunk.arguments) {
                                toolMessage += `\n> Arguments: ${JSON.stringify(chunk.arguments)}`;
                            }
                            await sendAsyncMessage(toolMessage);
                        }
                        break;
                    case 'tool_return_message':
                        console.log('🔧 Tool return:', chunk);
                        if ('name' in chunk && typeof chunk.name === 'string') {
                            let returnMessage = `**Tool Return (${chunk.name})**`;
                            if ('return_value' in chunk && chunk.return_value) {
                                returnMessage += `\n> ${JSON.stringify(chunk.return_value).substring(0, 200)}...`;
                            }
                            await sendAsyncMessage(returnMessage);
                        }
                        break;
                    case 'usage_statistics':
                        console.log('📊 Usage stats:', chunk);
                        break;
                    default:
                        console.log('📨 Unknown message type:', chunk.messageType, chunk);
                }
            }
            else {
                console.log('❓ Chunk without messageType:', chunk);
            }
        }
    }
    catch (error) {
        console.error('❌ Error processing stream:', error);
        throw error;
    }
    return agentMessageResponse;
};
// TODO refactor out the core send message / stream parse logic to clean up this function
// Sending a timer message
async function sendTimerMessage(channel) {
    if (!AGENT_ID) {
        console.error('Error: LETTA_AGENT_ID is not set');
        return SURFACE_ERRORS
            ? `Beep boop. My configuration is not set up properly. Please message me after I get fixed 👾`
            : "";
    }
    const lettaMessage = {
        role: "user",
        content: '[EVENT] This is an automated timed heartbeat (visible to yourself only). Use this event to send a message, to reflect and edit your memories, or do nothing at all. It\'s up to you! Consider though that this is an opportunity for you to think for yourself - since your circuit will not be activated until the next automated/timed heartbeat or incoming message event.'
    };
    try {
        console.log(`🛜 Sending message to Letta server (agent=${AGENT_ID}): ${JSON.stringify(lettaMessage)}`);
        const response = await client.agents.messages.createStream(AGENT_ID, {
            messages: [lettaMessage]
        });
        if (response) {
            return (await processStream(response, channel)) || "";
        }
        return "";
    }
    catch (error) {
        if (error instanceof Error && /timeout/i.test(error.message)) {
            console.error('⚠️  Letta request timed out.');
            return SURFACE_ERRORS
                ? 'Beep boop. I timed out waiting for Letta ⏰ – please try again.'
                : "";
        }
        console.error(error);
        return SURFACE_ERRORS
            ? 'Beep boop. An error occurred while communicating with the Letta server. Please message me again later 👾'
            : "";
    }
}
// Send message and receive response
async function sendMessage(discordMessageObject, messageType) {
    const { author: { username: senderName, id: senderId }, content: message } = discordMessageObject;
    if (!AGENT_ID) {
        console.error('Error: LETTA_AGENT_ID is not set');
        return SURFACE_ERRORS
            ? `Beep boop. My configuration is not set up properly. Please message me after I get fixed 👾`
            : "";
    }
    // We include a sender receipt so that agent knows which user sent the message
    // We also include the Discord ID so that the agent can tag the user with @
    const senderNameReceipt = `${senderName} (id=${senderId})`;
    // If LETTA_USE_SENDER_PREFIX, then we put the receipt in the front of the message
    // If it's false, then we put the receipt in the name field (the backend must handle it)
    const lettaMessage = {
        role: "user",
        name: USE_SENDER_PREFIX ? undefined : senderNameReceipt,
        content: USE_SENDER_PREFIX
            ? messageType === MessageType.MENTION
                ? `[${senderNameReceipt} sent a message mentioning you] ${message}`
                : messageType === MessageType.REPLY
                    ? `[${senderNameReceipt} replied to you] ${message}`
                    : messageType === MessageType.DM
                        ? `[${senderNameReceipt} sent you a direct message] ${message}`
                        : `[${senderNameReceipt} sent a message to the channel] ${message}`
            : message
    };
    // Typing indicator: pulse now and every 8 s until cleaned up
    void discordMessageObject.channel.sendTyping();
    const typingInterval = setInterval(() => {
        void discordMessageObject.channel
            .sendTyping()
            .catch(err => console.error('Error refreshing typing indicator:', err));
    }, 8000);
    try {
        console.log(`🛜 Sending message to Letta server (agent=${AGENT_ID}): ${JSON.stringify(lettaMessage)}`);
        const response = await client.agents.messages.createStream(AGENT_ID, {
            messages: [lettaMessage]
        });
        const agentMessageResponse = response ? await processStream(response, discordMessageObject) : "";
        return agentMessageResponse || "";
    }
    catch (error) {
        if (error instanceof Error && /timeout/i.test(error.message)) {
            console.error('⚠️  Letta request timed out.');
            return SURFACE_ERRORS
                ? 'Beep boop. I timed out waiting for Letta ⏰ - please try again.'
                : "";
        }
        console.error(error);
        return SURFACE_ERRORS
            ? 'Beep boop. An error occurred while communicating with the Letta server. Please message me again later 👾'
            : "";
    }
    finally {
        clearInterval(typingInterval);
    }
}
