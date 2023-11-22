#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    Slixmpp OMEMO plugin
    Copyright (C) 2010  Nathanael C. Fritz
    Copyright (C) 2019 Maxime “pep” Buquet <pep@bouah.net>
    This file is part of slixmpp-omemo.

    See the file LICENSE for copying permission.
"""

import os
import re
import sys
import logging
from getpass import getpass
from argparse import ArgumentParser
import random
import requests
from datetime import date
import json
import copy

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


# Used by the ChatBot
LEVEL_DEBUG = 0
LEVEL_ERROR = 1

class XMPPBot(ClientXMPP):
    """
    A simple Slixmpp bot that will query a number of different popular API's for Large Language models
    """

    eme_ns = 'eu.siacs.conversations.axolotl'
    cmd_prefix = '!'
    today = date.today()
    debug_level: int = LEVEL_ERROR  # LEVEL_ERROR or LEVEL_DEBUG
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/json'
    }
    def __init__(self, jid, password,room,nick,config_path,mode,api_host):
        ClientXMPP.__init__(self, jid, password)

        self.prefix_re: re.Pattern = re.compile('^%s' % self.cmd_prefix)
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

# TODO see if if/else blocks can be made more readable
    def api_call(self, mfrom, decoded_msg):
        if mfrom.bare not in self.user_sessions:
            self.user_sessions[mfrom.bare] = copy.deepcopy(self.character_card)

        if self.character_card['format'] == "alpaca":
            self.user_sessions[mfrom.bare]['prompt'] += f'{decoded_msg}\n### Response:\n'
        elif self.character_card['format'] == "chatml":
            self.user_sessions[mfrom.bare]['prompt'] += f'{decoded_msg}<|im_end|>\n<|im_start|>assistant'
        elif self.character_cardp['format'] == "pygmalion":
            self.user_sessions[mfrom.bare]['prompt'] += f' {decoded_msg}\n{self.user_sessions[mfrom.bare]["name"]}:'
        if self.mode == "llama.cpp":
            response = requests.post(f'{self.api_host}/completion', headers=self.headers,
                                     data=json.dumps(self.user_sessions[mfrom.bare]))
            response_json = json.loads(response.text)
            response = response_json['content']
        elif self.mode == "kobold.cpp":
            response = requests.post(f'{self.api_host}/api/v1/generate', headers=self.headers,
                                     data=json.dumps(self.user_sessions[mfrom.bare]))
            response_json = response.json()
            response = response_json['results'][0]['text']

        if self.character_card['format'] == "alpaca":
            self.user_sessions[mfrom.bare]['prompt'] += f'{response}\n### Instruction:\n'
        elif self.character_card['format'] == "chatml":
            # Clear incorrectly formmated chatml
            response = response.replace("<|im_end|>","")
            response = response.replace("<|im_start|>", "")
            self.user_sessions[mfrom.bare]['prompt'] += f'{response}<|im_end|>\n<|im_start|>user'
        elif self.character_cardp['format'] == "pygmalion":
            response = response.replace("\n" + self.user_sessions[mfrom.bare]['name'] + ": ", "")
            response = response.replace("You:", "")
            self.user_sessions[mfrom.bare]['prompt'] += response + '\nYou: '
        return response
        
    def is_command(self, body: str) -> bool:
        return self.prefix_re.match(body) is not None

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

        return None

    async def cmd_help(self, mto: JID, mtype: str) -> None:
        body = (
            'Hello my name is ' + args.jid+'\n' 
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
        self.user_sessions[mto.bare] = copy.deepcopy(self.character_card) # Deepcopy prevents passing reference
                                                                           # use it in all cases
        body = '''NOTICE: CONTEXT WINDOW CLEARED SUCCESSFULLY.'''
        return await self.encrypted_reply(mto, mtype, body)

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
        mfrom = mto = msg['from']
        mtype = msg['type']

        if mtype not in ('chat', 'normal'):
            return None

        if not self['xep_0384'].is_encrypted(msg):
            if self.debug_level == LEVEL_DEBUG:
                await self.plain_reply(mto, mtype, f"Echo unencrypted message: {msg['body']}")
            return None

        try:
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
                    response = self.api_call(mfrom, decoded_msg)
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
                        help="Backend JSON profile defaults to config/defaults.json", default=DEFAULT_CONFIG_PATH)
    # What style of API call to use when querying in the API
    parser.add_argument("-m", "--mode", dest="mode",
                        help="Whether to use kobold.cpp or llama.cpp stype API calls. Defaults to llama.cpp", default=DEFAULT_MODE)
    # The host where API calls are being served
    parser.add_argument("-a", "--api-host", dest="api_host",
                        help="The host where the API is being served from. Defaults to http://locahost:8080", default=DEFAULT_API_HOST)

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

    xmpp = XMPPBot(args.jid, args.password,args.room,args.nick, args.system_prompt,args.mode,args.api_host)
    xmpp.register_plugin('xep_0030')  # Service Discovery
    xmpp.register_plugin('xep_0199')  # XMPP Ping
    xmpp.register_plugin('xep_0380')  # Explicit Message Encryption
    xmpp.register_plugin('xep_0045')  # Multi User Chat
    try:
        xmpp.register_plugin(
            'xep_0384',
            {
                'data_dir': args.data_dir,
            },
            module=slixmpp_omemo,
        )  # OMEMO
    except (PluginCouldNotLoad,):
        log.exception('And error occured when loading the omemo plugin.')
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
