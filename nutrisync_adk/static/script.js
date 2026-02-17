const GUEST_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11";
const API_URL = "/api/chat";

const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');

// Auto-scroll to bottom
function scrollToBottom() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function appendMessage(role, text, chartData = null) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message');
    msgDiv.classList.add(role === 'user' ? 'user-message' : 'bot-message');

    // Parse Markdown
    msgDiv.innerHTML = marked.parse(text);

    chatHistory.appendChild(msgDiv);

    // Render Chart if available
    if (chartData && chartData.image_base64) {
        const chartContainer = document.createElement('div');
        chartContainer.classList.add('chart-container');

        const img = document.createElement('img');
        img.src = `data:image/png;base64,${chartData.image_base64}`;
        img.alt = chartData.caption || "Chart";
        img.style.maxWidth = "100%";

        chartContainer.appendChild(img);

        // Add caption if present
        if (chartData.caption) {
            const caption = document.createElement('div');
            caption.style.color = '#333';
            caption.style.fontSize = '0.8rem';
            caption.style.marginTop = '5px';
            caption.style.textAlign = 'center';
            caption.innerText = chartData.caption;
            chartContainer.appendChild(caption);
        }

        chatHistory.appendChild(chartContainer);
    }

    scrollToBottom();
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;

    // Clear input
    userInput.value = '';

    // Append User Message
    appendMessage('user', text);

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: text,
                guest_id: GUEST_ID
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Append Bot Response
        appendMessage('model', data.text, data.chart);

    } catch (error) {
        console.error('Error:', error);
        appendMessage('model', '**Error**: Could not connect to the server.');
    }
}

// Event Listeners
sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendMessage();
    }
});
