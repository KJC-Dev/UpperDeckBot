# 🔭 UpperDeckBot: The AI-Powered chatbot that connects you to a whole ✨constellation✨ of open source tools

UpperDeckBot is a powerful and flexible XMPP chatbot built using the slixmpp Python Library, designed to act as an End to End Encrypted(E2EE) bridge for accessing internal network resources when in the outside world.

## ✅ Key Features:

1. 🔒 Security: UpperDeckBot leverages security focused the XMPP implementation of OMEMO to effortlessly create a end to end encrypted(E2EE) connections to large language models hosted on your local network, ensuring reduced latency and enhanced security.
2. 🎨 Image Creation: Just describe what you want to the chatbot and it will create it via a function call Stable Diffusion Webui's API 
3. 📚 Retrieval Augmented Generation: UpperDeckBot Searches for information using locally hosted offline mirrors of Wikipedia to answer user requests allowing you to avoid hallucinated answers.
4. 💬 TTS support: Integration with [XTTSv2](https://huggingface.co/coqui/XTTS-v2) allows for lifelike text to speech capabilities for UpperDeckBot’s responses.
5. 🛠 Customizable: UpperDeckBot is designed for easy modification of both the system prompt as well as the addition of per users profiles as needed for different use cases.
6. 🫱🏻‍🫲🏿 Cross-platform: UpperDeckBot works flawlessly on Windows, macOS, and Linux operating systems and can be run seperately from the services it connects to.

## 🚧 Work in Progress Items:

1. Response streaming for decrease the time before the user can begin reading the response
2. Integration with CLIP models for analysis of user uploaded images
3. Parallelization of application processes for performence improvement

## Getting Started:

1. Clone the Repository
   ```
   git clone https://github.com/KJC-Dev/UpperDeckBot
   cd UpperDeckBot
   ```
2. Install the required dependencies using pip:
   ```
   pip install -r requirements.txt
   ```
2. Configure UpperDeckBot by editing the your chosen profile in the config folder with your desired settings.

4. Start the bot replacing the varibles with your own :
   ```
   python3 xmpp.py -j $JIDVAR -p $PASSWORDVAR -s $CONFIGPATH -m $MODEVAR -a $HOSTVAR
   ```
5. Connect to the bot using your favorite OMEMO supporting XMPP client and start chatting. 


## **License**:

UpperDeckBot is released under the GPLv3 License. 

Contributions welcome. This project is still growing and finding its footing.
