#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import random
import asyncio
import logging
import time
from getpass import getpass
from argparse import ArgumentParser

from slixmpp import ClientXMPP, JID
from slixmpp.exceptions import IqTimeout, IqError, XMPPError
from slixmpp.stanza import Message
import slixmpp_omemo
from slixmpp_omemo import PluginCouldNotLoad, MissingOwnKey, EncryptionPrepareException
from slixmpp_omemo import UndecidedException, UntrustedException, NoAvailableSession
from omemo.exceptions import MissingBundleException

# globals
log = logging.getLogger(__name__)
versionNumber=0.8
lockout = False

class WhisperBot(ClientXMPP):
    """
    A simple xmpp bot that will responed to certain commmands.
    """

    eme_ns = 'eu.siacs.conversations.axolotl'


    def __init__(self, jid, password, room, nick):
        ClientXMPP.__init__(self, jid, password)
        self.room = room
        self.nick = nick
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.message_handler)
        self.use_message_ids = True


    def diceRoll(self):
        return "Dice Roll Result: " + str(random.randrange(1, 7))
        

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
        # Groupchat does not work with current library version May 12th 2021
        # uncomment the following section when it does

        if self.room:
            for rooms in self.room.split(sep=","):
                logging.debug("joining: %s" % rooms)
                self.plugin['xep_0045'].join_muc(rooms, self.nick)


    def message_handler(self, msg: Message) -> None:
        asyncio.ensure_future(self.message(msg))

    async def message_keyword_handler(self, msg, isPrivateMessage):
        botCommandResponse = "That command was not recognized did you try !help"
        responseMessage = msg
        mfrom = msg['from']
        # Dispaly the version number of the bot.

        if isPrivateMessage:
            encrypted = msg['omemo_encrypted']
            body = await self['xep_0384'].decrypt_message(encrypted, mfrom, True)
            messageText = body.decode("utf8")
            messageText = messageText.replace("'","")
            print("Decoded message: "+ messageText)
            
            # first check for bang commands
            if messageText.startswith("!"):
                if messageText.startswith("!breadstick"):
                    botCommandResponse = "Its a dollar a breadstick!"
                elif messageText.startswith("!rtd"):
                    botCommandResponse = self.diceRoll()
                elif messageText.startswith("!version"):
                    botCommandResponse = "upperdeckbot version: " + versionNumber
                elif messageText.startswith("!help"):
                    botCommandResponse = "Help pages are for suckas read the source code. JK I just need to write this"
                else:
                    botCommandResponse = "That command was not recognized did you try !help"
            else:
                print("AI Access Started")
                botCommandResponse = os.popen("python3 /home/mx/xmppbot-main/aiPrompter.py '"+messageText+"'").read()
                print("Decoded response: "+ botCommandResponse)
                print("AI Access Complete")
        return botCommandResponse

    async def plain_reply(self, msg):
        messageBody = msg['body']
        response = self.message_keyword_handler(messageBody, False)
        msg.reply(response).send()

    async def message(self, msg: Message, allow_untrusted: bool = False) -> None:
        """
        Process incoming message stanzas. Be aware that this also
        includes MUC messages and error messages. It is usually
        a good idea to check the messages's type before processing
        or sending replies.

        Arguments:
            msg -- The received message stanza. See the documentation
                   for stanza objects and the Message stanza to see
                   how it may be used.
        """
        # Throw out non relevent messages and self sent messages to prevent infinite response loops
        if msg['type'] not in ('chat', 'normal', 'groupchat') or msg['mucnick'] == self.nick:
            return None

        # the library for this does not support groupchat encryption so we do group chats unencrypted
        # thus we handle groupchats via a simple unencrypted response
        if msg['type'] == ('groupchat'):
            self.plain_reply(msg)
        # if the message is private we handle it via a more complex decryption and reencryption process
        else:
            try:
                botCommandResponse = self.message_keyword_handler(msg,True)
                await self.encrypted_reply(msg, botCommandResponse)
                return None
            except (MissingOwnKey,):
                # The message is missing our own key, it was not encrypted for
                # us, and we can't decrypt it.
                await self.message(
                    msg,
                    'I can\'t decrypt this message as it is not encrypted for me.',
                )
                return None
            except (NoAvailableSession,) as exn:
                # We received a message from that contained a session that we
                # don't know about (deleted session storage, etc.). We can't
                # decrypt the message, and it's going to be lost.
                # Here, as we need to initiate a new encrypted session, it is
                # best if we send an encrypted message directly. XXX: Is it
                # where we talk about self-healing messages?
                await self.encrypted_reply(
                    msg,
                    'I can\'t decrypt this message as it uses an encrypted '
                    'session I don\'t know about.',
                )
                return None
            except (UndecidedException, UntrustedException) as exn:
                # We received a message from an untrusted device. We can
                # choose to decrypt the message nonetheless, with the
                # `allow_untrusted` flag on the `decrypt_message` call, which
                # we will do here. This is only possible for decryption,
                # encryption will require us to decide if we trust the device
                # or not. Clients _should_ indicate that the message was not
                # trusted, or in undecided state, if they decide to decrypt it
                # anyway.
                await self.message(
                    msg,
                    "Your device '%s' is not in my trusted devices." % exn.device,
                )
                # We resend, setting the `allow_untrusted` parameter to True.
                await self.message(msg, allow_untrusted=True)
                return None
            except (EncryptionPrepareException,):
                # Slixmpp tried its best, but there were errors it couldn't
                # resolve. At this point you should have seen other exceptions
                # and given a chance to resolve them already.
                await self.message(msg, 'I was not able to decrypt the message.')
                return None
            except (Exception,) as exn:
                print('An error occured while attempting decryption.\n%r' % exn)
                raise
            return None


    async def encrypted_reply(self, original_msg, body):
        """Helper to reply with encrypted messages"""

        mto = original_msg['from']
        mtype = original_msg['type']
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
                # The library prevents us from sending a message to an
                # untrusted/undecided barejid, so we need to make a decision here.
                # This is where you prompt your user to ask what to do. In
                # this bot we will automatically trust undecided recipients.
                self['xep_0384'].trust(exn.bare_jid, exn.device, exn.ik)
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
                            original_msg,
                            'Could not find keys for device "%d" of recipient "%s". Skipping.' %
                            (error.device, error.bare_jid),
                        )
                        jid = JID(error.bare_jid)
                        device_list = expect_problems.setdefault(jid, [])
                        device_list.append(error.device)
            except (IqError, IqTimeout) as exn:
                self.plain_reply(
                    original_msg,
                    'An error occurred while fetching information on a recipient.\n%r' % exn,
                )
                return None
            except Exception as exn:
                await self.plain_reply(
                    original_msg,
                    'An error occured while attempting to encrypt.\n%r' % exn,
                )
                raise

        return None


if __name__ == '__main__':
    # Setup the command line arguments.
    parser = ArgumentParser(description=WhisperBot.__doc__)
    # configfile this will overwrite any

    # Output verbosity options
    parser.add_argument("-q", "--quiet", help="set logging to ERROR",
                        action="store_const", dest="loglevel",
                        const=logging.ERROR, default=logging.INFO)
    parser.add_argument("-d", "--debug", help="set logging to DEBUG",
                        action="store_const", dest="loglevel",
                        const=logging.DEBUG, default=logging.INFO)
    # JID and password options. will overwrite the
    parser.add_argument("-j", "--jid", dest="jid",
                        help="JID to use")
    parser.add_argument("-p", "--password", dest="password",
                        help="password to use")
    parser.add_argument("-r", "--rooms", dest="rooms",
                        help="rooms to join(comma separated list)")
    parser.add_argument("-n", "--nick", dest="nick",
                        help="set a custom nickname")

    # Data dir for omemo plugin
    DATA_DIR = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'omemo',
    )
    parser.add_argument("--data-dir", dest="data_dir",
                        help="data directory", default=DATA_DIR)

    args = parser.parse_args()

    # Setup logging.
    logging.basicConfig(level=args.loglevel,
                        format='%(levelname)-8s %(message)s')

    if args.jid is None:
        args.jid = input("Username: ")
    if args.password is None:
        args.password = getpass("Password: ")

    # Ensure OMEMO data dir is created
    os.makedirs(args.data_dir, exist_ok=True)

    xmpp = WhisperBot(args.jid, args.password, args.rooms, args.nick)
    xmpp.register_plugin('xep_0012')  # Last Activity
    xmpp.register_plugin('xep_0030')  # Service Discovery
    xmpp.register_plugin('xep_0045')  # Multi-User Chat
    xmpp.register_plugin('xep_0060')  # PubSub
    xmpp.register_plugin('xep_0085')  # Chat State Notifications
    xmpp.register_plugin('xep_0092')  # Software Version
    xmpp.register_plugin('xep_0128')  # Service Discovery Extensions
    xmpp.register_plugin('xep_0199')  # XMPP Ping
    xmpp.register_plugin('xep_0380')  # Explicit Message Encryption


    # NOTE TO FUTURE SELF THE PLUGIN DOES NOT CURRENTLY SUPPORT GROUP CHATS. RIP
    # The encryption was more or less bolted on to the code later so uhh I didn't feel confident adding it to the
    # above list.
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
