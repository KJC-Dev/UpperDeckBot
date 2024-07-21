#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import re
import threading
import sys
import logging
from collections.abc import AsyncGenerator
from aiohttp import ClientSession
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

import tts_middleware

script_dir = sys.argv[0].split("/")[:-1]
full_path = ""
for path_part in script_dir[1:]:
    full_path += "/" + path_part
if len(full_path) > 0:
    full_path += "/"

log = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = "config/defaults.json"
DEFAULT_MODE = "llama.cpp"
DEFAULT_API_HOST = "127.0.0.1:8080"
DEFAULT_VOICE_PATH = full_path + "input/female-1.wav"
DEFAULT_SD_HOST = "http://127.0.0.1:7860/sdapi/v1/txt2img"

DEFAULT_HEADERS = {
    "User-Agent": "aiohttp",
    "Content-Type": "application/json",
    "Connection": "keep-alive",
    "Accept": "text/event-stream",
}

DEFAULT_COMPLETION_OPTIONS = {
    # Llama-3 style prompt template shown in this example
    "prompt": f"<|start_header_id|>system<|end_header_id|>\n\nYou are a Zen master and mystical poet.<|eot_id|><|start_header_id|>user<|end_header_id|>\n\nWrite a short haiku about llamas.<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
    # ChatML style prompt template shown below
    # "prompt": f"<|im_start|>system\nYou are a Zen master and mystical poet.\n<|im_end|>\n<|im_start|>user\nWrite a short haiku about llamas.\n<|im_end|>\n<|im_start|>assistant\n",
    "temperature": 0.8,
    "top_k": 40,
    "top_p": 0.95,
    "min_p": 0.05,
    "repeat_penalty": 1.1,
    "n_predict": -1,
    "seed": -1,
    "id_slot": -1,
    "cache_prompt": False,
    # Likely need to add more stop tokens below to support more model types.
    "stop": ["<|eot_id|>", "<|im_end|>", "<|endoftext|>", "<|end|>", "</s>"],
    "stream": True,
}

DEFAULT_RESPONSE_BODY_START_STRING = "data: ".encode("utf-8")
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


class XMPPBotStream(threading.Thread):
    def run(self):
        self.current_response = ""
        self.str_mfrom = ""
        self.mfrom = JID()
        self.mfrom.bare = self.str_mfrom
        i = 0
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


class LlamaCppAPIClient:
    """headers and options can be overriden at constructions time or per inference call"""

    def __init__(self, base_url: str = "http://localhost:8080", headers: dict = {}, options: dict = {}):
        # override defaults with whatever userland passes into constructor
        self.base_url = base_url
        self.headers = DEFAULT_HEADERS
        self.headers.update(headers)
        self.options = DEFAULT_COMPLETION_OPTIONS
        self.options.update(options)

    async def stream_completion(
        self, chat_thread: list[dict] = [], format: str = "Llama-3"
    ) -> AsyncGenerator[dict, None]:
        """Stream LLaMA.cpp HTTP Server API POST /completion responses"""
        try:
            # convert chat_thread to a template formatted prompt string
            prompt = chat_to_prompt(chat_thread=chat_thread, format=format)

            # set the HTTP headers and /completion API options
            url = self.base_url.rstrip("/") + "/completion"
            combined_headers = self.headers
            combined_options = self.options
            combined_options.update({"prompt": prompt})

            async with ClientSession() as session:
                async with session.post(url=url, headers=combined_headers, json=combined_options) as response:
                    if not response.status == 200:
                        raise Exception(f"HTTP Response: {response.status}")

                    async for raw_line in response.content:
                        if len(raw_line) == 1:
                            continue
                        if raw_line[: len(DEFAULT_RESPONSE_BODY_START_STRING)] != DEFAULT_RESPONSE_BODY_START_STRING:
                            # FIXME: this is brittle code, not sure if another json decoder and skip the "data: " part...
                            raise Exception("Invalid response body starting string, unable to parse response...")
                        line = raw_line.decode("utf-8")[len(DEFAULT_RESPONSE_BODY_START_STRING) :]
                        yield json.loads(line)
        except Exception as e:
            raise e


def chat_to_prompt(chat_thread: list[dict], format: str) -> str:
    """Accepts a list of dicts in the OpenAI style chat thread and returns string with specified prompt template applied."""
    # There must be a better way to do this e.g.
    # https://github.com/ggerganov/llama.cpp/commit/8768b4f5ea1de69a4cace0481fdba70d89a47e47

    # Initialize result as empty string
    result = ""

    # Check if the chat is not empty or only contains system/user roles
    if len(chat_thread) == 0:
        raise ValueError("Chat thread cannot be empty.")

    for _, message in enumerate(chat_thread):
        # Error check to ensure 'role' and 'content' keys exist in each dict
        try:
            role = message["role"]
            content = message["content"]
        except KeyError as e:
            raise ValueError(f"Each chat thread item must contain both 'role' and 'content' keys: {e}")

        if role not in ["system", "user", "assistant"]:
            raise ValueError("Chat thread only supports 'system', 'user', and 'assistant' roles.")

        # TODO Apply chat template formats or jinja templates and return prompt string.
        # Could use jinja templates e.g. https://github.com/vllm-project/vllm/blob/main/examples/template_chatml.jinja
        # This is clunky hacky but gets a minimal PoC going quick...
        match format:
            # template["ChatML"] = f"<|im_start|>system\n{system_prompt}\n<|im_end|>\n<|im_start|>user\n{user_prompt}\n<|im_end|>\n<|im_start|>assistant\n"
            # Do not prepend the BOS as that seems to cause hallucinations...
            # llama_tokenize_internal: Added a BOS token to the prompt as specified by the model but the prompt also starts with a BOS token. So now the final prompt starts with 2 BOS tokens. Are you sure this is what you want?
            case "ChatML":
                result += f"<|im_start|>{role}\n{content}\n<|im_end|>\n"
            # template["Llama-3"] =  f"<|start_header_id|>system<|end_header_id|>\n\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{user_prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
            # Unclear if need to prepend BOS to start: https://huggingface.co/meta-llama/Meta-Llama-3-8B/discussions/35 .. does not seem to hurt anything...
            # Don't add BOS, llama.cpp server side is doing that: llama_tokenize_internal: Added a BOS token to the prompt as specified by the model but the prompt also starts with a BOS token. So now the final prompt starts with 2 BOS tokens. Are you sure this is what you want?
            case "Llama-3":
                result += f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
            # Phi-3 might not support system prompt, but try anyway. "{{ bos_token }}{% for message in messages %}\n{% if message['role'] == 'user' %}\n{{ '<|user|>\n' + message['content'] + '<|end|>' }}\n{% elif message['role'] == 'system' %}\n{{ '<|system|>\n' + message['content'] + '<|end|>' }}\n{% elif message['role'] == 'assistant' %}\n{{ '<|assistant|>\n'  + message['content'] + '<|end|>' }}\n{% endif %}\n{% if loop.last and add_generation_prompt %}\n{{ '<|assistant|>' }}\n{% endif %}\n{% endfor %}"
            # skip prepending BOS for now, haven't tested as much as above but seems fine without it...
            case "Phi-3":
                # if result == "":
                #     result += "<s>\n"
                result += f"<|{role}|>\n{content}<|end|>\n"
            case "Raw":
            # just concatanate all content fields if userland wants to pass raw string
                result += f"{content}"
            case _:
                raise NotImplementedError(f"{format} not in list of supported formats e.g. ChatML, Llama-3, Phi-3, Raw...")

    # chat threads must end by cueing the assistant to begin generation
    match format:
        case "ChatML":
            result += "<|im_start|>assistant\n"
        case "Llama-3":
            result += "<|start_header_id|>assistant<|end_header_id|>\n\n"
        case "Phi-3":
            result += "<|assistant|>\n"
    return result


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

    def __init__(self, jid, password, room, nick, config_path, mode, api_host, dry_run, tts, voice_only, echo_bot_mode):
        ClientXMPP.__init__(self, jid, password)

        self.command_prefix_re: re.Pattern = re.compile('^%s' % self.cmd_prefix)
        self.txt2img_prefix_re: re.Pattern = re.compile('^%s' % self.txt2img_prefix)
        self.cmd_re: re.Pattern = re.compile('^%s(?P<command>\w+)(?:\s+(?P<args>.*))?' % self.cmd_prefix)

        self.add_event_handler("session_start", self.start)
        #  self.add_event_handler("groupchat_message", self.muc_message)
        # noinspection PyTypeChecker
        self.register_handler(CoroutineCallback('Messages',
                                                MatchXPath(f'{{{self.default_ns}}}message'),
                                                self.message_handler,
                                                ))
        with open(config_path, 'r') as file:
            self.character_card = json.load(file)
        if tts is not None:
            self.ac = tts_middleware.TTSAudioController(temperature=.75)
            self.tp = tts_middleware.TTSTextProcessor()

        self.room = room
        self.nick = nick
        self.mode = mode
        self.api_host = api_host
        self.user_sessions = {}
        self.dry_run = dry_run
        self.tts = tts
        self.voice_only = voice_only
        self.echo_bot_mode = echo_bot_mode

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
        regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        find_urls_in_string = re.compile(regex, re.IGNORECASE)
        url = find_urls_in_string.search(line)
        if url is not None and url.group(0) is not None:
            # print("URL parts: " + str(
            #    url.groups()))  # OUTPUT: ('http://www.google.com', 'http', 'google.com', 'com', None, None)
            # print("URL" + url.group(0).strip())  # OUTPUT: http://www.google.com
            return url.group(0).strip()
        return line

    async def api_call(self, mfrom, mtype, prompt):

        # if in echo debug mode simply return the prompt discarding any context
        if self.echo_bot_mode:
            self.user_sessions[mfrom.bare] = copy.deepcopy(self.character_card)
            return prompt

        # --Pre Function 2: Generic HTTP/HTTPS--
        # for line in prompt.splitlines():
        # if self.http_prefix in line or self.https_prefix in line:
        # new_line = line.replace(self.http_prefix, 'Link:' + self.http_prefix)
        # new_line = line.replace(self.https_prefix, 'Link:' + self.https_prefix)
        # extracted_url = await self.extract_url(line)

        # new_line += "\nContents: " + await self.http_request(url=extracted_url)
        # prompt = prompt.replace(line, new_line)
        # -------------------------------------------------------#

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
                self.user_sessions[mfrom.bare]['prompt'] += f'{prompt}\n{self.user_sessions[mfrom.bare]["name"]}:'
            case "vicuna":
                self.user_sessions[mfrom.bare]['prompt'] += f'{prompt}\nASSISTANT: '
            case "llama3":
                self.user_sessions[mfrom.bare][
                    'prompt'] += f'{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n'
            case "phi-3":
                self.user_sessions[mfrom.bare]['prompt'] += f'{prompt}<|end|>\n<|assistant|>\n'
            case _:
                raise "Config Error: No matching prompt format found"

        # current_session = XMPPBotStream()
        # current_session.mfrom = mfrom
        # current_session.start()
        response = await self.api_session(mfrom, self.mode)

        # log.info(current_session.current_response)
        # Post functions

        # -------------------------------------------------------#
        # --Post Function 1: txt2img generation--
        for line in response.splitlines():
            if self.txt2img_prefix in line:
                await self.encrypted_reply(mto=mfrom, mtype=mtype, body=await self.upload_txt2img(txt2img_prompt=line))
        # -------------------------------------------------------#
        # -------------------------------------------------------#

        match self.character_card['format']:
            case "alpaca":
                self.user_sessions[mfrom.bare]['prompt'] += f'{response}\n### Instruction:\n'
            case "chatml":
                # Clear incorrectly formmated chatml
                response = response.replace("<|im_end|>", "")
                response = response.replace("<|im_start|>", "")
                response = response.replace("\nuser", "")
                # Add correctly formatted chatml
                self.user_sessions[mfrom.bare]['prompt'] += f'{response}<|im_end|>\n<|im_start|>user'
            case "mistral":
                # clean badly formatted mistral close brackets
                response = response.split("\n[", 1)[0]
                self.user_sessions[mfrom.bare]['prompt'] += f' {response} </s>'
            case "pygmalion":
                response = response.replace("\n" + self.user_sessions[mfrom.bare]['name'] + ": ", "")
                response = response.replace("You:", "")
                self.user_sessions[mfrom.bare]['prompt'] += response + '\nYou: '
            case "vicuna":
                self.user_sessions[mfrom.bare]['prompt'] += response + '\nUSER: '
            case "llama3":
                response = response.replace("!assistant", "")
                response = response.replace("?assistant", "")
                response = response.replace(".assistant", "")
                self.user_sessions[mfrom.bare]['prompt'] += response + '<|start_header_id|>user<|end_header_id|>\n\n'
            case "phi-3":
                response = response.replace("<|end|>", "")
                self.user_sessions[mfrom.bare]['prompt'] += f'{response}<|end|>\n<|user|>\n'
        return response

    async def api_session(self, mfrom, api_mode):
        # making the call
        response_json = {}
        try:
            match api_mode:
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

        except KeyError:
            raise requests.HTTPError(
                "INVALID JSON ENDPOINT DETECTED. PLEASE SPECIFY THE CORRECT ENDPOINT THE PROGRAM ARGUMENTs")

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
        for idx, p_tag in enumerate(p_tags):
            for code_tag in code_tags:
                if code_tag in p_tag and code_tag != '':
                    p_tags[idx] = p_tag.replace(code_tag, " " + code_tag + " ")
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
        # noinspection PyTypedDict
        upload_link = await self.plugin['xep_0454'].upload_file(filename=Path(img_path))

        return upload_link

    def is_command(self, body: str) -> bool:
        return self.command_prefix_re.match(body) is not None

    def is_txt2img(self, body: str) -> bool:
        return self.txt2img_prefix_re.match(body) is not None

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

    def llm_available(self):
        test_json = '{"n_predict": 1,"max_length": 1,"prompt": ""}'
        try:
            match self.mode:
                case "llama.cpp":
                    response = requests.post(f'{self.api_host}/completion', headers=self.headers,
                                             data=test_json)
                    response_json = json.loads(response.text)
                    response = response_json['content']
                case "kobold.cpp":
                    response = requests.post(f'{self.api_host}/api/v1/generate', headers=self.headers,
                                             data=test_json)
                    response_json = response.json()
                    response = response_json['results'][0]['text']
            return True

        except KeyError:
            raise json.JSONDecodeError("ERROR: MISMATCHED JSON RESPONSE FROM HOST. ARE YOU USING THE CORRECT MODE FOR "
                                       "YOUR BACKEND?",doc="",pos=0)

    async def dry_run_mode(self) -> None:
        self.user_sessions["dryrun@example.com"] = copy.deepcopy(self.character_card)
        dry_run_jid = JID()
        dry_run_jid.bare = "dryrun@example.com"
        # output = " "+str(time.time())
        while True:
            time.sleep(0.5)
            prompt = input("USER     ")
            output = await self.api_call(dry_run_jid, "chat", prompt)
            log.info(output)

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
                    if self.tts:
                        response = self.tp.preprocess_text(input_text=response,
                                                           rules_list=tts_middleware.default_rule_list)
                        response_split = self.tp.split_text(input_text=response)
                        self.ac.run_model(sentences=response_split, speakers=[self.tts])
                        # noinspection PyTypedDict
                        await self.encrypted_reply(mto, mtype, await self.plugin['xep_0454'].upload_file(
                            filename=Path(f'{full_path}final.mp3')))
                        os.remove("final.mp3")
                    if not self.voice_only:
                        await self.encrypted_reply(mto, mtype, response)

        except (MissingOwnKey,):
            # The message is missing our own key, it was not encrypted for
            # us, and we can't decrypt it.
            await self.plain_reply(
                mto, mtype,
                'NOTICE: MESSAGE NOT ENCRYPTED FOR US. TRYING TO ADD TO KEYSTORE',
            )
        except (NoAvailableSession,) as exn:
            # We received a message from that contained a session that we
            # don't know about (deleted session storage, etc.). We can't
            # decrypt the message, and it's going to be lost.
            # Here, as we need to initiate a new encrypted session, it is
            # best if we send an encrypted message directly.
            await self.encrypted_reply(
                mto, mtype,
                'ERROR: MESSAGE USES AN ENCRYPTED '
                'SESSION I DON\'T KNOW ABOUT.',
            )
        except (UndecidedException, UntrustedException) as exn:
            # We received a message from an untrusted device. We can
            # choose to decrypt the message nonetheless, with the
            # `allow_untrusted` flag on the `message_handler` call, which
            # we will do here. This is only possible for decryption,
            # encryption will require us to decide if we trust the device
            # or not. Clients _should_ indicate that the message was not
            # trusted, or in undecided state, if they decide to decrypt it
            # anyway.
            #    await self.plain_reply(
            #        mto, mtype,
            #        f'NOTICE: NEW DEVICE "{exn.device}" DETECTED FOR ACCOUNT "{exn.bare_jid}". '
            #        f'WELCOME, NEW OR RETURNING USER.',
            #    )
            # We resend, setting the `allow_untrusted` parameter to True.
            await self.message_handler(msg, allow_untrusted=True)
        except (EncryptionPrepareException,):
            # Slixmpp tried its best, but there were errors it couldn't
            # resolve. At this point you should have seen other exceptions
            # and given a chance to resolve them already.
            await self.plain_reply(mto, mtype, 'ERROR: UNABLE TO DECRYPT MESSAGE.')
        except (Exception,) as exn:
            if exn is not ValueError('Invalid padding bytes.'):
                await self.plain_reply(mto, mtype, 'ERROR: EXCEPTION OCCURRED WHILE PROCESSING MESSAGE. IF ERROR '
                                                   'PERSISTS CONTACT ADMIN. ERROR IS AS FOLLOWS.\n%r' % exn)
            raise
        #   xmpp.disconnect(reason='ERROR: EXCEPTION OCCURRED' % exn)

        return None

    # noinspection PyTypeChecker
    async def plain_reply(self, mto: JID, mtype: str, body):
        """
        Helper to reply to messages
        """

        msg = self.make_message(mto=mto, mtype=mtype)
        msg['body'] = body
        return msg.send()

    # noinspection PyTypeChecker
    async def encrypted_reply(self, mto: JID, mtype: str, body):
        """Helper to reply with encrypted messages"""

        msg = self.make_message(mto=mto, mtype=mtype)
        msg['eme']['namespace'] = self.eme_ns
        msg['eme']['name'] = self['xep_0380'].mechanisms[self.eme_ns]

        expect_problems = {}  # type: #Optional[Dict[JID, List[int]]]

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
                        await self.plain_reply(
                            mto, mtype,
                            f'Could not find keys for device "{error.device}"'
                            f' of recipient "{error.bare_jid}". Skipping.',
                        )
                        jid = JID(error.bare_jid)
                        device_list = expect_problems.setdefault(jid, [])
                        device_list.append(error.device)
            except (IqError, IqTimeout) as exn:
                await self.plain_reply(
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
    parser.add_argument("-t", "--tts", dest="tts",
                        help="In tts mode the bot responds with an mp3 file containing. "
                             "Can be used in addition to or in place of text responses. "
                             "--tts must be followed by a path to a .wav file to clone from",
                        default=None)

    parser.add_argument("--voice-only", dest="voice_only",
                        help="Do not respond using text. Intended for use in combination with --tts for voice only "
                             "responses.",
                        action='store_true', default=None)
    parser.add_argument("--dry-run", dest="dry_run",
                        help="DEBUG: Open a direct session with the LLM, bypassing "
                             "the XMPP server. This option effectively turns the CLI",
                        action='store_true', default=None)
    parser.add_argument("--echo", dest="echo_bot_mode",
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

    if args.voice_only is not None:
        voice_only = True
    else:
        voice_only = False

    if args.echo_bot_mode is not None:
        echo_bot_mode = True
    else:
        echo_bot_mode = False

    xmpp = XMPPBot(jid=args.jid,
                   password=args.password,
                   room=args.room,
                   nick=args.nick,
                   config_path=args.system_prompt,
                   mode=args.mode,
                   api_host=args.api_host,
                   dry_run=dry_run,
                   tts=args.tts,
                   voice_only=voice_only,
                   echo_bot_mode=echo_bot_mode)

    if not echo_bot_mode and not xmpp.llm_available():
        exit(1)

    if xmpp.dry_run:
        log.debug("DRY RUN MODE FLAG DETECTED BYPASSING XMPP CONNECTION")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(xmpp.dry_run_mode())
        loop.run_forever()
    else:

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
