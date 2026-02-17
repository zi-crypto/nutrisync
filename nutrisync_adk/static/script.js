const GUEST_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11";
const API_URL = "/api/chat";

const chatHistory = document.getElementById('chat-history');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const uploadBtn = document.getElementById('upload-btn');
const fileInput = document.getElementById('file-input');
const previewContainer = document.getElementById('image-preview-container');
const imagePreview = document.getElementById('image-preview');
const clearImageBtn = document.getElementById('clear-image');

let currentImageBase64 = null;

// Auto-scroll to bottom
function scrollToBottom() {
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function appendMessage(role, text, chartData = null, imageBase64 = null) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message');
    msgDiv.classList.add(role === 'user' ? 'user-message' : 'bot-message');

    let contentHtml = "";

    // If there's an image (for user messages primarily)
    if (imageBase64) {
        contentHtml += `<img src="${imageBase64}" style="max-width: 200px; border-radius: 8px; display: block; margin-bottom: 5px;">`;
    }

    // Parse Markdown
    contentHtml += marked.parse(text || "");
    msgDiv.innerHTML = contentHtml;

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

    if (!text && !currentImageBase64) return;

    // Capture state
    const msgText = text;
    const msgImage = currentImageBase64;

    // Clear input and preview
    userInput.value = '';
    clearImage();

    // Append User Message
    appendMessage('user', msgText, null, msgImage);

    try {
        const payload = {
            guest_id: GUEST_ID,
            message: msgText
        };

        if (msgImage) {
            payload.image = msgImage;
        }

        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
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

// Image Handling
uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            currentImageBase64 = e.target.result;
            imagePreview.src = currentImageBase64;
            previewContainer.style.display = 'inline-block';
        };
        reader.readAsDataURL(file);
    }
});

function clearImage() {
    fileInput.value = '';
    currentImageBase64 = null;
    previewContainer.style.display = 'none';
}

clearImageBtn.addEventListener('click', clearImage);

// Auto-resize textarea
userInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});

async function loadHistory() {
    try {
        const response = await fetch(`/api/history/${GUEST_ID}`);
        if (!response.ok) return;

        const history = await response.json();
        // Clear default message if history exists
        if (history.length > 0) {
            chatHistory.innerHTML = '';
        }

        history.forEach(msg => {
            let chartData = null;

            // Check for charts in tool_calls
            if (msg.tool_calls) {
                // Handle both array of dicts (from DB JSONB) and potential stringified variations
                let tools = msg.tool_calls;
                if (typeof tools === 'string') {
                    try { tools = JSON.parse(tools); } catch (e) { }
                }

                if (Array.isArray(tools)) {
                    // Look for ANY tool response that contains image_base64
                    const chartTool = tools.find(t => {
                        if (!t.response) return false;

                        let r = t.response;
                        if (typeof r === 'string') {
                            try { r = JSON.parse(r); } catch (e) { return false; }
                        }

                        return r && r.image_base64;
                    });

                    if (chartTool) {
                        let resp = chartTool.response;
                        if (typeof resp === 'string') {
                            try { resp = JSON.parse(resp); } catch (e) { }
                        }

                        if (resp.image_base64) {
                            chartData = {
                                image_base64: resp.image_base64,
                                caption: resp.caption
                            };
                        }
                    }
                }
            }

            appendMessage(msg.role, msg.content, chartData);
        });

        scrollToBottom();

    } catch (error) {
        console.error("Failed to load history:", error);
    }
}

// Init
loadHistory();

// Event Listeners
sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault(); // Prevent newline
        sendMessage();
        // Reset height
        userInput.style.height = 'auto';
    }
});
