🔭 UpperDeckBot: The AI-Powered chatbot that gives you to a whole ✨constellation✨ of open source tools 

UpperDeckBot is a powerful and flexible XMPP chatbot built using the slixmpp Python Library, designed to act as an End to End Encrypted(E2EE) bridge for accessing internal network resources when in the outside world.

✅ Key Features:

1. 🔒 Security: UpperDeckBot leverages security focused XMPP extentions such as OMEMO to effortlessly create a End to end encrypted(E2EE) connection to large language models hosted on your network, ensuring quick response times and enhanced security.
2. 🎨 Multimodal: UpperDeckBot can generate images via Stable Diffusion and search for information on locally hosted offline mirrors of Wikipedia(using XOWA) as needed to answer user requests without ever leaving your network
3. 🛠 Customizable: UpperDeckBot is designed for easy modification of both the system prompt as well as the addition of per users profiles as needed for different use cases
4. 🫱🏻‍🫲🏿 Cross-platform: UpperDeckBot works flawlessly on Windows, macOS, and Linux operating systems and can be run seperately from the services it connects to.

🚧 Work in Progress Items:

1. Response streaming for decrease the time before the user can begin reading the response
2. Integration with CLIP models for analysis of user uploaded images
3. Parallelization of application processes for performence improvement

Getting Started:

1. Clone the Repository
   ```
   git clone https://github.com/KJC-Dev/UpperDeckBot
   cd UpperDeckBot
   ```
2. Install the required dependencies using pip:
   ```
   pip install -r requirements.txt
   ```
2. Configure UpperDeckBot by editing the `config.yml` file with your desired settings.

4. Start the bot replacing the varibles with your own :
   ```
   python3 xmpp.py -j $JIDVAR -p $PASSWORDVAR -s $CONFIGPATH -m $MODEVAR -a $HOSTVAR
   ```
5. Connect to the bot using your favorite OMEMO supporting XMPP client and start chatting. 

Contributions and Support:

**License**:

UpperDeckBot is released under the GPLv3 License. 

Contributions welcome. This project is still growing and finding its footing.
