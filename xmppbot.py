#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import re
import secrets
import threading
import sys
import logging
from PIL import Image
from io import BytesIO
import base64
from getpass import getpass
from argparse import ArgumentParser
import random
from pathlib import Path
import time
import subprocess

import requests
from datetime import date
import json
import copy

from bs4 import BeautifulSoup
from slixmpp import ClientXMPP, JID
from slixmpp.exceptions import IqTimeout, IqError
from slixmpp.stanza import Message
from slixmpp.xmlstream.handler import CoroutineCallback
from slixmpp.xmlstream.matcher import MatchXPath
import slixmpp_omemo
from slixmpp_omemo import PluginCouldNotLoad, MissingOwnKey, EncryptionPrepareException
from slixmpp_omemo import UndecidedException, UntrustedException, NoAvailableSession
from omemo.exceptions import MissingBundleException

log = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = "config/defaults.json"
DEFAULT_MODE = "llama.cpp"
DEFAULT_API_HOST = "127.0.0.1:8080"
DEFAULT_SD_HOST = "http://127.0.0.1:7860/sdapi/v1/txt2img"

HEADERS = {
    'accept': 'application/json',
    'Content-Type': 'application/json'
}

# Used by the ChatBot
LEVEL_DEBUG = 0
LEVEL_ERROR = 1

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


script_dir = sys.argv[0].split("/")[:-1]
full_path = ""
for path_part in script_dir[1:]:
    full_path += "/" + path_part
if len(full_path) > 0:
    full_path += "/"

class XMPPBotStream(threading.Thread):


    def run(self):
        self.current_response = ""
        self.str_mfrom = ""
        self.mfrom = JID()
        self.mfrom.bare = self.str_mfrom
        i = 0;
        # code for the background job goes here
        while i < 10:
            self.current_response = subprocess.check_output(["curl",
                                                             "-s",
                                                             "-X",
                                                             "GET",
                                                             "http://localhost:5001/api/extra/generate/check",
                                                             "-H",
                                                             "accept: application/json",
                                                             "-H",
                                                             "Content-Type: application/json"])
            i += 1
            time.sleep(5)
            print(self.current_response)
            xmpp.encrypted_reply(self.mfrom, "chat", self.current_response)

class XMPPBot(ClientXMPP):
    """
    A simple Slixmpp bot that will query a number of different popular API's for Large Language models
    """

    eme_ns = 'eu.siacs.conversations.axolotl'
    cmd_prefix = '!'
    txt2img_prefix = 'txt2img://'
    http_prefix = 'http://'
    https_prefix = 'https://'
    wikipedia_prefix = 'wiki://'
    today = date.today()
    debug_level: int = LEVEL_ERROR  # LEVEL_ERROR or LEVEL_DEBUG
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }

    def __init__(self, jid, password, room, nick, config_path, mode, api_host, dry_run,voicemail,no_text,echo_run):
        ClientXMPP.__init__(self, jid, password)

        self.command_prefix_re: re.Pattern = re.compile('^%s' % self.cmd_prefix)
        self.txt2img_prefix_re: re.Pattern = re.compile('^%s' % self.txt2img_prefix)
        self.cmd_re: re.Pattern = re.compile('^%s(?P<command>\w+)(?:\s+(?P<args>.*))?' % self.cmd_prefix)

        self.add_event_handler("session_start", self.start)
        #  self.add_event_handler("groupchat_message", self.muc_message)
        self.register_handler(CoroutineCallback('Messages',
                                                MatchXPath(f'{{{self.default_ns}}}message'),
                                                self.message_handler,
                                                ))
        with open(config_path, 'r') as file:
            self.character_card = json.load(file)
        self.room = room
        self.nick = nick
        self.mode = mode
        self.api_host = api_host
        self.user_sessions = {}
        self.dry_run = dry_run
        self.voicemail = voicemail
        self.no_text = no_text
        self.echo_run = echo_run

    def start(self, _event) -> None:
        """
        Process the session_start event.

        Typical actions for the session_start event are
        requesting the roster and broadcasting an initial
        presence stanza.

        Arguments:
            event -- An empty dictionary. The session_start
                     event does not provide any additional
                     data.
        """

        self.send_presence()
        self.get_roster()
        self.plugin['xep_0045'].join_muc(self.room,
                                         self.nick,
                                         # If a room password is needed, use:
                                         # password=the_room_password,
                                         )

    async def extract_url(self, line):
        regex = (r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        find_urls_in_string = re.compile(regex, re.IGNORECASE)
        url = find_urls_in_string.search(line)
        if url is not None and url.group(0) is not None:
            # print("URL parts: " + str(
            #    url.groups()))  # OUTPUT: ('http://www.google.com', 'http', 'google.com', 'com', None, None)
            # print("URL" + url.group(0).strip())  # OUTPUT: http://www.google.com
            return url.group(0).strip()
        return line

    async def api_call(self, mfrom, mtype, prompt):

        # if in debug echo simply return the prompt
        if self.echo_run:
            return prompt

        # --Pre Function 2: Generic HTTP/HTTPS--
        for line in prompt.splitlines():
            if self.http_prefix in line or self.https_prefix in line:
                new_line = line.replace(self.http_prefix, 'Link:' + self.http_prefix)
                new_line = line.replace(self.https_prefix, 'Link:' + self.https_prefix)
                extracted_url = await self.extract_url(line)

                new_line += "\nContents: " + await self.http_request(url=extracted_url)
                prompt = prompt.replace(line, new_line)
            # -------------------------------------------------------#
            # --Pre Function 2: Local Wikitext Lookup--
            if self.wikipedia_prefix in line:
                line = line.replace("_"," ")
                new_line = line.replace(self.wikipedia_prefix, ': ' + self.https_prefix)
                
        # -------------------------------------------------------#

        # Preprocessing the prompt format
        match self.character_card['format']:
            case "alpaca":
                self.user_sessions[mfrom.bare]['prompt'] += f'{prompt}\n### Response:\n'
            case "mistral":
                self.user_sessions[mfrom.bare]['prompt'] += f'[INST] {prompt}[/INST] '
            case "chatml":
                self.user_sessions[mfrom.bare]['prompt'] += f'user\n{prompt}<|im_end|>\n<|im_start|>assistant\n'
            case "pygmalion":
                self.user_sessions[mfrom.bare]['prompt'] += f' {prompt}\n{self.user_sessions[mfrom.bare]["name"]}:'
            case _:
                raise "Config Error: No matching prompt format found"


       # current_session = XMPPBotStream()
       # current_session.mfrom = mfrom
       # current_session.start()
        response = await self.api_session(mfrom)

        #log.info(current_session.current_response)
        # Post functions
        match self.character_card['format']:
            case "alpaca":
                self.user_sessions[mfrom.bare]['prompt'] += f'{response}\n### Instruction:\n'
            case "chatml":
                # Clear incorrectly formmated chatml
                response = response.replace("<|im_end|>", "")
                response = response.replace("<|im_start|>", "")
                response = response.replace("\nuser", "")
                # Add correcly formated chatml
                self.user_sessions[mfrom.bare]['prompt'] += f'{response}<|im_end|>\n<|im_start|>user'
            case "mistral":
                # clean badly formated mistral close brackets
                response = response.split("\n[", 1)[0]
                self.user_sessions[mfrom.bare]['prompt'] += f' {response} </s>'
            case "pygmalion":
                response = response.replace("\n" + self.user_sessions[mfrom.bare]['name'] + ": ", "")
                response = response.replace("You:", "")
                self.user_sessions[mfrom.bare]['prompt'] += response + '\nYou: '

            # -------------------------------------------------------#
            # --Post Function 1: txt2img generation--
        for line in response.splitlines():
            if self.txt2img_prefix in line:
                await self.encrypted_reply(mto=mfrom,mtype="chat", body=await self.upload_txt2img(txt2img_prompt=line))
            # -------------------------------------------------------#
        return response

    async def api_session(self, mfrom):
        # making the call
        match self.mode:
            case "llama.cpp":
                response = requests.post(f'{self.api_host}/completion', headers=self.headers,
                                         data=json.dumps(self.user_sessions[mfrom.bare]))
                response_json = json.loads(response.text)
                return response_json['content']

            case "kobold.cpp":
                response = requests.post(f'{self.api_host}/api/v1/generate', headers=self.headers,
                                         data=json.dumps(self.user_sessions[mfrom.bare]))
                response_json = response.json()
                return response_json['results'][0]['text']

    # leave 500 tokens left for actual answering the question and followup questions
    async def http_request(self, url: str):
        session = requests.session()

        try:
            req = session.get(url)
        except:
            return "INFORMATION: AN ERROR OCCURED WHEN ACCESSING THE WEBPAGE. PLEASE INFORM THE USER."
        doc = BeautifulSoup(req.content, features="lxml")
        p_tags = [tag.get_text(strip=True) for tag in doc.findAll('p')]
        code_tags = [tag.get_text(strip=True) for tag in doc.findAll('code')]
        a_tags = [tag.get_text(strip=True) for tag in doc.findAll('a')]

     #   code_tags = ["--help","--clblast"]
        for idx,p_tag in enumerate(p_tags):
            for code_tag in code_tags:
                if code_tag in p_tag and code_tag != '':
                    p_tags[idx] = p_tag.replace(code_tag," "+code_tag+" ")
#            for a_tag in a_tags:
#                if a_tag in p_tag and a_tag != '':
#                    p_tags[idx] = p_tag.replace(a_tag," "+a_tag+" ")



        paragraphs = p_tags
        combined_text = ""
        for paragraph in paragraphs:
            if len(combined_text) < self.character_card['max_context_length'] - 500:
                combined_text += paragraph + " "
        return combined_text

    async def upload_txt2img(self, txt2img_prompt: str):
        data = {
            "prompt": txt2img_prompt,
            "negative_prompt": "watermark,text,signature,author signature,nsfw,nude,hentai",
            # todo make these not hardcoded
            "steps": 20  # todo make these not hardcoded
        }
        response = requests.post(DEFAULT_SD_HOST, data=json.dumps(data))
        # Load the response JSON into a python dictionary
        response_dict = json.loads(response.text)

        # Extract base64 encoded image data from response JSON
        img_bytes = bytes(response_dict["images"][0], 'utf-8')

        # Convert the bytes to a binary format and open it using PIL
        img_bin = BytesIO(base64.b64decode(img_bytes))
        img = Image.open(img_bin)

        # Save the image into a file named "output.png" in the current directory
        current_time = int(time.time())
        img_path = str(sys.path[0]) + "/images/" + str(current_time) + ".png"
        img.save(img_path)
        upload_link = await self.plugin['xep_0454'].upload_file(filename=Path(img_path))

        return upload_link

    def is_command(self, body: str) -> bool:
        return self.command_prefix_re.match(body) is not None

    def is_txt2img(self, body: str) -> bool:
        return self.txt2img_prefix_re.match(body) is not None

    def is_http(self, body: str) -> bool:
        return self.http_prefix.match(body) is not None

    async def handle_command(self, mto: JID, mtype: str, body: str) -> None:
        match = self.cmd_re.match(body)
        if match is None:
            return None

        groups = match.groupdict()
        cmd = groups['command']
        # args = groups['args']

        if cmd == 'help':
            await self.cmd_help(mto, mtype)
        elif cmd == 'rtd':
            await self.cmd_rtd(mto, mtype)
        elif cmd == 'resetcontext':
            await self.cmd_resetcontext(mto, mtype)
        elif cmd == 'rc':
            await self.cmd_resetcontext(mto, mtype)
        elif cmd == 's':

            await self.cmd_shell(mto, mtype, body)

        return None

    async def cmd_help(self, mto: JID, mtype: str) -> None:
        body = (
                'Hello my name is ' + args.jid + '\n'
                                                 'The following commands are available:\n'
                                                 f'{self.cmd_prefix}rc Clear your current conversation with the chatbot\n'
                                                 f'{self.cmd_prefix}rtd roll dice to decide a random number\n'
        )
        return await self.encrypted_reply(mto, mtype, body)

    async def cmd_rtd(self, mto: JID, mtype: str) -> None:
        body = (
                "Dice Roll Result: " + str(random.randrange(1, 7))
        )
        return await self.encrypted_reply(mto, mtype, body)

    async def cmd_resetcontext(self, mto: JID, mtype: str) -> None:
        self.user_sessions[mto.bare] = copy.deepcopy(self.character_card)  # Deepcopy prevents passing reference
        # use it in all cases
        body = '''NOTICE: CONTEXT WINDOW CLEARED SUCCESSFULLY.'''
        return await self.encrypted_reply(mto, mtype, body)

    async def cmd_shell(self, mto: JID, mtype: str, body: str) -> None:
        if mto.bare == "kyler@upperdeckcommittee.xyz":
            body = subprocess.check_output(body[3:], shell=True).decode('utf-8')
            return await self.encrypted_reply(mto, mtype, body)
        else:
            return None

    async def dry_run_mode(self) -> None:
        self.user_sessions["dryrun@example.com"] = copy.deepcopy(self.character_card)
        dry_run_jid = JID()
        dry_run_jid.bare = "dryrun@example.com"
        # output = " "+str(time.time())
        while True:
            time.sleep(0.5)
            prompt = input("USER     ")
            #  self.api_call_preprocessing
            # response = api
            output = await self.api_call(dry_run_jid, "chat", prompt)
            log.info(output[1:])

    async def message_handler(self, msg: Message, allow_untrusted: bool = False) -> None:
        """
        Process incoming message stanzas. Be aware that this also
        includes MUC messages and error messages. It is usually
        a good idea to check the message's type before processing
        or sending replies.

        Arguments:
            msg -- The received message stanza. See the documentation
                   for stanza objects and the Message stanza to see
                   how it may be used.
        """
        # Break away from the normal flow in a dry run
        if self.dry_run:
            await self.dry_run_mode()

        mfrom = mto = msg['from']
        mtype = msg['type']

        if mtype not in ('chat', 'normal'):
            return None

        if not self['xep_0384'].is_encrypted(msg):
            if self.debug_level == LEVEL_DEBUG:
                await self.plain_reply(mto, mtype, f"Echo unencrypted message: {msg['body']}")
            return None

        try:
            if mfrom.bare not in self.user_sessions:
                self.user_sessions[mfrom.bare] = copy.deepcopy(self.character_card)
            #   self.user_sessions[mfrom.bare]['genkey'] = secrets.token_hex(20) # assign a unique key to the user session
            encrypted = msg['omemo_encrypted']
            body = await self['xep_0384'].decrypt_message(encrypted, mfrom, allow_untrusted)
            # decrypt_message returns Optional[str]. It is possible to get
            # body-less OMEMO message (see KeyTransportMessages), currently
            # used for example to send heartbeats to other devices.
            if body is not None:
                decoded_msg = body.decode('utf8')
                if self.is_command(decoded_msg):
                    await self.handle_command(mto, mtype, decoded_msg)

                else:
                    response = await self.api_call(mfrom, mtype, decoded_msg)
                    if self.voicemail:
                        # TODO remove hard coding and make more pythonic
                        file = open(full_path+"input.txt", "w")
                        file.write(response) # change this to response for normal voicemail mode
                        file.close()
                        exec(open(full_path +'tts.py').read())
                        os.remove(full_path + "input.txt")
                        await self.encrypted_reply(mto, mtype, await self.plugin['xep_0454'].upload_file(
                            filename=Path(full_path+"output.mp3")))
                    if not self.no_text:
                        await self.encrypted_reply(mto, mtype, response)

        except (MissingOwnKey,):
            # The message is missing our own key, it was not encrypted for
            # us, and we can't decrypt it.
            await self.plain_reply(
                mto, mtype,
                'NOTICE: NEW ENCRYPTION KEY DETECTED. REGISTERING NEW DEVICE IN KEYSTORE',
            )
        except (NoAvailableSession,) as exn:
            # We received a message from that contained a session that we
            # don't know about (deleted session storage, etc.). We can't
            # decrypt the message, and it's going to be lost.
            # Here, as we need to initiate a new encrypted session, it is
            # best if we send an encrypted message directly. XXX: Is it
            # where we talk about self-healing messages?
            await self.encrypted_reply(
                mto, mtype,
                'ERROR: MESSAGE USES AN ENCRYPTED '
                'SESSION I DON\'T KNOW ABOUT.',
            )
        except (UndecidedException, UntrustedException) as exn:
            # We received a message from an untrusted device. We can
            # choose to decrypt the message nonetheless, with the
            # `allow_untrusted` flag on the `decrypt_message` call, which
            # we will do here. This is only possible for decryption,
            # encryption will require us to decide if we trust the device
            # or not. Clients _should_ indicate that the message was not
            # trusted, or in undecided state, if they decide to decrypt it
            # anyway.
            await self.plain_reply(
                mto, mtype,
                f'NOTICE: NEW DEVICE "{exn.device}" DETECTED FOR ACCOUNT "{exn.bare_jid}". '
                f'WELCOME, NEW OR RETURNING USER.',
            )
            # We resend, setting the `allow_untrusted` parameter to True.
            await self.message_handler(msg, allow_untrusted=True)
        except (EncryptionPrepareException,):
            # Slixmpp tried its best, but there were errors it couldn't
            # resolve. At this point you should have seen other exceptions
            # and given a chance to resolve them already.
            await self.plain_reply(mto, mtype, 'ERROR: UNABLE TO DECRYPT MESSAGE.')
        except (Exception,) as exn:
            await self.plain_reply(mto, mtype, 'ERROR: EXCEPTION OCCURRED WHILE ATTEMPTING DECRYPTION.\n%r' % exn)
            raise

        return None

    async def plain_reply(self, mto: JID, mtype: str, body):
        """
        Helper to reply to messages
        """

        msg = self.make_message(mto=mto, mtype=mtype)
        msg['body'] = body
        return msg.send()

    async def encrypted_reply(self, mto: JID, mtype: str, body):
        """Helper to reply with encrypted messages"""

        msg = self.make_message(mto=mto, mtype=mtype)
        msg['eme']['namespace'] = self.eme_ns
        msg['eme']['name'] = self['xep_0380'].mechanisms[self.eme_ns]

        expect_problems = {}  # type: Optional[Dict[JID, List[int]]]

        while True:
            try:
                # `encrypt_message` excepts the plaintext to be sent, a list of
                # bare JIDs to encrypt to, and optionally a dict of problems to
                # expect per bare JID.
                #
                # Note that this function returns an `<encrypted/>` object,
                # and not a full Message stanza. This combined with the
                # `recipients` parameter that requires for a list of JIDs,
                # allows you to encrypt for 1:1 as well as groupchats (MUC).
                #
                # `expect_problems`: See EncryptionPrepareException handling.
                recipients = [mto]
                encrypt = await self['xep_0384'].encrypt_message(body, recipients, expect_problems)
                msg.append(encrypt)
                return msg.send()
            except UndecidedException as exn:
                # Automatically trust undecided recipients.
                await self['xep_0384'].trust(exn.bare_jid, exn.device, exn.ik)
            # TODO: catch NoEligibleDevicesException
            except EncryptionPrepareException as exn:
                # This exception is being raised when the library has tried
                # all it could and doesn't know what to do anymore. It
                # contains a list of exceptions that the user must resolve, or
                # explicitely ignore via `expect_problems`.
                # TODO: We might need to bail out here if errors are the same?
                for error in exn.errors:
                    if isinstance(error, MissingBundleException):
                        # We choose to ignore MissingBundleException. It seems
                        # to be somewhat accepted that it's better not to
                        # encrypt for a device if it has problems and encrypt
                        # for the rest, rather than error out. The "faulty"
                        # device won't be able to decrypt and should display a
                        # generic message. The receiving end-user at this
                        # point can bring up the issue if it happens.
                        self.plain_reply(
                            mto, mtype,
                            f'Could not find keys for device "{error.device}"'
                            f' of recipient "{error.bare_jid}". Skipping.',
                        )
                        jid = JID(error.bare_jid)
                        device_list = expect_problems.setdefault(jid, [])
                        device_list.append(error.device)
            except (IqError, IqTimeout) as exn:
                self.plain_reply(
                    mto, mtype,
                    'An error occured while fetching information on a recipient.\n%r' % exn,
                )
                return None
            except Exception as exn:
                await self.plain_reply(
                    mto, mtype,
                    'An error occured while attempting to encrypt.\n%r' % exn,
                )
                raise

        return None


if __name__ == '__main__':
    # Setup the command line arguments.
    parser = ArgumentParser(description=XMPPBot.__doc__)

    # Output verbosity options.
    parser.add_argument("-q", "--quiet", help="set logging to ERROR",
                        action="store_const", dest="loglevel",
                        const=logging.ERROR, default=logging.INFO)
    parser.add_argument("-d", "--debug", help="set logging to DEBUG",
                        action="store_const", dest="loglevel",
                        const=logging.DEBUG, default=logging.INFO)

    # JID and password options.
    parser.add_argument("-j", "--jid", dest="jid",
                        help="JID to use")
    parser.add_argument("-p", "--password", dest="password",
                        help="password to use")
    parser.add_argument("-r", "--room", dest="room",
                        help="MUC room to join")
    parser.add_argument("-n", "--nick", dest="nick",
                        help="MUC nickname")
    # Data dir for omemo plugin
    DATA_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'omemo',
    )
    parser.add_argument("--data-dir", dest="data_dir",
                        help="data directory", default=DATA_DIR)

    # JSON file that sets the starting prompt for a session
    parser.add_argument("-s", "--system-prompt", dest="system_prompt",
                        help="Backend JSON profile defaults to config/defaults.json",
                        default=DEFAULT_CONFIG_PATH)
    # What style of API call to use when querying in the API
    parser.add_argument("-m", "--mode", dest="mode",
                        help="Whether to use kobold.cpp or llama.cpp stype API calls. Defaults to llama.cpp",
                        default=DEFAULT_MODE)
    # The host where API calls are being served
    parser.add_argument("-a", "--api-host", dest="api_host",
                        help="The host where the API is being served from. Defaults to http://locahost:8080",
                        default=DEFAULT_API_HOST)
    parser.add_argument("--voicemail", dest="voicemail",
                        help="In voicemail mode the bot responds using an mp3 to generate a text to speech file. "
                             "Can be used in addition to or in place of text responses",
                        action='store_true',default=None)
    parser.add_argument("--no-text", dest="no_text",
                        help="Do not respond using text. Implies --voicemail",
                        action='store_true',default=None)
    parser.add_argument("--dry-run", dest="dry_run",
                        help="DEBUG: Connect normally but open a direct session with the underlying LLM, bypassing "
                             "XMPP on any subsequent messages",
                        action='store_true', default=None)
    parser.add_argument("--echo-run", dest="echo_run",
                        help="DEBUG: Connect normally but echo the users input back to them, bypassing The LLM "
                             "entirely",
                        action='store_true', default=None)

    args = parser.parse_args()
    # Setup logging.
    logging.basicConfig(level=args.loglevel,
                        format='%(levelname)-8s %(message)s')

    # prompt for creds in case arguments are not supplied
    if args.jid is None:
        args.jid = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")

    # Setup the ChatBot and register plugins. Note that while plugins may
    # have interdependencies, the order in which you register them does
    # not matter.

    # Ensure OMEMO data dir is created
    os.makedirs(args.data_dir, exist_ok=True)

    if args.dry_run is not None:
        dry_run = True
    else:
        dry_run = False

    if args.voicemail is not None:
        voicemail = True
    else:
        voicemail = False

    if args.no_text is not None:
        no_text = True
        voicemail = True
    else:
        no_text = False

    if args.echo_run is not None:
        echo_run = True
    else:
        echo_run = False


    xmpp = XMPPBot(jid=args.jid,
                   password=args.password,
                   room=args.room,
                   nick=args.nick,
                   config_path=args.system_prompt,
                   mode=args.mode,
                   api_host=args.api_host,
                   dry_run=dry_run,
                   voicemail=voicemail,
                   no_text=no_text,
                   echo_run=echo_run)

    xmpp.register_plugin('xep_0030')  # Service Discovery
    xmpp.register_plugin('xep_0199')  # XMPP Ping
    xmpp.register_plugin('xep_0380')  # Explicit Message Encryption
    xmpp.register_plugin('xep_0045')  # Multi User Chat
    xmpp.register_plugin('xep_0363')  # file upload
    xmpp.register_plugin('xep_0454')  # OMEMO file upload
    try:
        xmpp.register_plugin(
            'xep_0384',
            {
                'data_dir': args.data_dir,
            },
            module=slixmpp_omemo,
        )  # OMEMO
    except (PluginCouldNotLoad,):
        log.exception('And error occurred when loading the omemo plugin.')
        sys.exit(1)

    # Connect to the XMPP server and start processing XMPP stanzas.
    xmpp.connect()
    xmpp.process()

"""
⠀⠀⠀⠀⡾⣦⡀⠀⠀⡀⠀⣰⢷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⣠⠗⠛⠽⠛⠋⠉⢳⡃⢨⢧⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⣰⠋⠁⠀⠀⠀⠀⠀⠀⠙⠛⢾⡈⡏⢧⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣼⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠸⢦⡀⠀⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⢈⠟⠓⠶⠞⠒⢻⣿⡏⢳⡀⠀⠀⠀⠀⢸⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⡴⢉⠀⠀⠀⠀⠀⠈⠛⢁⣸⠇⠀⠀⠀⠀⢺⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⢧⣸⡁⠀⠀⣀⠀⠀⣠⠾⠀⠀⠀⠀⠀⠀⣹⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠉⠓⢲⠾⣍⣀⣀⡿⠃⠀⠀⠀⠀⠀⠀⢸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⢀⡗⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡼⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⢸⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⣸⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠺⠦⠤⠤⣤⣄⣀⣀⡀⠀⠀⠀⠀⠀
⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉⠳⣦⣄⠀⠀
⠀⠀⢀⡷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⣆⠀
⠀⠀⣼⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣆
⠀⠀⣏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿
⠀⠀⢹⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼
⠀⠀⠀⣏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡞
⠀⠀⠀⠈⢷⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⡇
⠀⠀⠀⠀⠈⢻⣦⣀⠀⣏⠀⠀⠀⠀⠀⠀⢸⡆⠀⠀⢠⡄⠀⠀⠀⠀⠀⢀⡿⠀
⠀⠀⠀⠀⠀⠀⠻⡉⠙⢻⡆⠀⠀⠀⠀⠀⡾⠚⠓⣖⠛⣧⡀⠀⠀⠀⢀⡾⠁⠀
⠀⠀⠀⠀⠀⠀⠀⠙⡇⢀⡿⣦⡀⠀⢀⡴⠃⠀⠀⠈⣷⢈⠷⡆⠀⣴⠛⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠛⠚⠀⢸⡇⣰⠏⠁⠀⠀⠀⠀⢉⠁⢸⠷⠼⠃⠀⠀⠀⠀
"""
