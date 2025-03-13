#### 🤖 **Hid**den**Ego** - Telegram Anonymous Messaging Bot Creator 
A robust solution for creating Telegram bots that empower anonymous messaging with powerful management and secure configurations.

---

#### 💰 **Donations**
If you find this project helpful, you can support its development through donations on the TON blockchain:

💎 Donate via TON:
```
ton://transfer/TechKraken.ton
```
```
UQCGk4IU5nm6dYWjXTx6vSQVOtKO4LQg3m8cRcq1eQo7vhCl
```

---

#### 🌟 **Overview**  
This project provides a comprehensive framework for building Telegram bots that handle anonymous messaging. With built-in features such as message forwarding, history management, and administrative controls, it allows you to deploy a secure and feature-rich messaging system. The project is designed with scalability and maintainability in mind, leveraging clear constants and modular code across configurations, handlers, and utility functions.

---

#### 📦 **Features**  
- **Anonymous Messaging**: Send messages without revealing your identity.  
- **History Management**: Options for sending messages with or without message history.  
- **Interactive Controls**: Inline buttons with emojis for actions like forwarding, blocking, and reading messages.  
- **Webhook Integration**: Seamless integration with Telegram’s webhook API.  
- **Secure Configuration**: Separation of sensitive data using secure configuration files.  
- **Live GitHub Comparison**:
Users can directly inspect and compare the deployed application with its GitHub repository counterpart using the `/safetycheck` command, ensuring complete transparency and fostering community trust.
- **Zero-Knowledge Security:** We only store a **partial hash** of encrypted data in the database, meaning even admins **cannot** decrypt it. Decryption is only possible when users provide their unique hash fragment, and the process happens entirely in memory—without being logged—ensuring ultimate privacy.

---

#### 🚀 **Installation**  
1. **Clone the Repository**:  
   ```bash
   git clone https://github.com/your-username/Telegram-Anonymous-Messaging-Bot-Creator.git
   cd Telegram-Anonymous-Messaging-Bot-Creator
   ```
2. **Install Dependencies**:  
   Ensure you have Python 3.8+ installed, then run:  
   ```bash
   pip install -r requirements.txt
   ```
3. **Prepare the Database**:  
   The project uses an SQLite database (`DATA.db`). No additional setup is required, but ensure the file is writable.

---

#### ⚙️ **Configuration**  
- **Environment Variables**:  
  Copy the provided `.env.example` to a new file named `.env` and update the following placeholders with your own credentials and configuration details:
  - `BOT_CREATOR_USERNAME` – Your bot's username.  
  - `MAIN_BOT_TOKEN` – Your Telegram Bot API token.  
  - `WEBHOOK_BASE_URL` – The URL to your webhook endpoint (use _ngrok_ for local development).  
  - `TG_SECRET_TOKEN` – A secure token for webhook verification.  
  - `TZ` – Set your timezone (e.g., `Asia/Tehran`).  
  - `FASTAPI_PORT` – The port number on which the API server will run.
  
  > **Note**: Ensure all sensitive data (tokens, secret keys) are kept secure and are not exposed publicly.

- **Secure Config File:**  
  The file `config.secure` contains the hashed master password. This secure configuration is managed via `secure_config.py` in the utils directory, ensuring that essential credentials remain protected and are separated from the main codebase.

---

#### 🔧 **Running the Bot**  
- **Development**:  
  Run the main bot creator script:  
  ```bash
  python bot_creator.py
  ```
  You must set a master password of at least 12 characters. This password is crucial as it encrypts all data stored in the database, ensuring maximum security and privacy.

- **Webhook Setup**:  
  For local testing, use [ngrok](https://ngrok.com/) to tunnel your local server.  
  ```bash
  ngrok http 8000
  ```
  Update `WEBHOOK_BASE_URL` in your `.env` file with the HTTPS URL provided by ngrok.

---

#### ☁️ **Deployment with Cloudflare (Production)**  
For a more secure production deployment, consider using Cloudflare Tunnel. You need a custom domain.
Follow these steps:

1. **Setup Cloudflare Tunnel**:  
   Create a new tmux session and start the tunnel:
   ```bash
   tmux new -s cloudflare-anonmsg -d && tmux attach -t cloudflare-anonmsg
   wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
   chmod +x cloudflared
   sudo mv cloudflared /usr/local/bin/
   cloudflared tunnel login
   ```
2. **Create and Configure Tunnel**:  
   After logging in, run:
   ```bash
   cloudflared tunnel create anon_webhook
   ```
   Copy the generated tunnel ID, then create a configuration file (e.g., `~/.cloudflared/anon_config.yml`) with the following content:
   ```yaml
   tunnel: <your-tunnel-id>
   credentials-file: /full/path/to/your/credentials.json

   ingress:
     - hostname: webhook.yourdomain.com
       service: http://localhost:8000
     - service: http_status:404
   ```
3. **Route the Tunnel**:  
   Configure the route for your domain:
   ```bash
   cloudflared tunnel route https anon_webhook webhook.yourdomain.com
   cloudflared tunnel --config ~/.cloudflared/anon_config.yml run anon_webhook
   ```

---

#### 🤝 **Contributing**  
Contributions are welcome! If you have ideas, bug fixes, or improvements, please open an issue or submit a pull request. Follow standard GitHub practices and ensure your code aligns with the project's guidelines.

---

#### 📞 **Contact & Support**  
For support or any inquiries, please reach out via:  
- **Telegram**: [Contact the Developer](https://t.me/ContactHydraBot)  
- **GitHub Repository**: [Telegram Anonymous Messaging Bot Creator](https://github.com/411A/Telegram-Anonymous-Messaging-Bot-Creator)
