import logging
import math
import random
import wave
import torch
from TTS import TTS
import TTS.TTS.utils.audio
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from TTS.config import BaseAudioConfig
import os
import sys
import re
import TTS.TTS.utils.audio.processor
from pydub import AudioSegment
from scipy.io import wavfile
import numpy

script_dir = sys.argv[0].split("/")[:-1]
full_path = ""
for path_part in script_dir[1:]:
    full_path += "/" + path_part
if len(full_path) > 0:
    full_path += "/"

default_min_sentence_length = 30
default_rule_list = [["...", "."],
                     ["..", "."],
                     ["\"", ""],
                     ["..", "."],
                     ["\"", ""],
                     ["’", "'"],
                     ["”", ""],
                     ["://", " "],
                     ["\n", " "],
                     [" -", ", "],
                     ["*", ""],
                     ["^", ""],
                     ["\t", ""],
                     ["  ", " "],
                     ["0.", "0 "],
                     ["1.", "1 "],
                     ["2.", "2 "],
                     ["3.", "3 "],
                     ["4.", "4 "],
                     ["5.", "5 "],
                     ["6.", "6 "],
                     ["7.", "7 "],
                     ["8.", "8 "],
                     ["9.", "9 "]]


def nearest_space(text, index):
    space_index = text.rfind(' ', 0, index)  # Find the last space before the given index
    if space_index == -1:  # If no space is found before the index
        space_index = text.find(' ')  # Find the first space after the index
    return space_index

class TTSAudioController:
    # device = "cpu"
    # List available 🐸TTS models
    # print(TTS().list_models())
    # Init TTS
    def __init__(self, top_k: int = 50,
                 top_p: float = 0.9,
                 temperature: float = 0.75,
                 repetition_penalty: float = 2.3,
                 gpt_cond_len: int = 999999,
                 pitch_fmax: int = 640,
                 pitch_fmin: int = 1):

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.config = XttsConfig()
        self.config.load_json(full_path + "XTTS-v2/config.json")
        self.model = Xtts.init_from_config(self.config)
        self.model.load_checkpoint(self.config, checkpoint_dir=full_path + "XTTS-v2/", eval=True)
        self.model.cuda()
        self.conf = BaseAudioConfig(pitch_fmax=pitch_fmax, pitch_fmin=pitch_fmin)
        self.ap = TTS.TTS.utils.audio.AudioProcessor(**self.conf)
        self.top_k = top_k
        self.top_p = top_p
        self.temperature = temperature
        self.repetition_penalty = repetition_penalty
        self.gpt_cond_len = gpt_cond_len

    def run_model(self, sentences: list, speakers: list, offset: int = 1):
        for speaker in speakers:
            if not os.path.exists(speaker):
                raise FileNotFoundError(f'Path to speaker {speaker} not found.')
                exit(1)
        metadata_path = f'{full_path}staging/metadata.txt'
        # os.remove(metadata_path)
        os.system(f'cp /dev/null {metadata_path}')

        for index, sentence in enumerate(sentences):
            if len(sentence) > 250:
                nearest_space_index=nearest_space(sentence, 250)
                new_sentence = sentence[nearest_space_index:]
                sentences[index] = sentence[:nearest_space_index]
                sentences.insert(index+1,new_sentence)
                logging.warning(
                    f'The sentence "{sentence[0:50]}...." exceeded the recommended length of 250 characters and has '
                    f'been split into two separate sentences')

        for index, sentence in enumerate(sentences):
            try:
                outputs = self.model.synthesize(text=sentence,
                                                config=self.config,
                                                speaker_wav=speakers,
                                                language="en",
                                                top_k=self.top_k,
                                                top_p=self.top_p,
                                                temperature=self.temperature,
                                                repetition_penalty=self.repetition_penalty,
                                                do_sample=True,
                                                gpt_cond_len=self.gpt_cond_len)
            except AssertionError:
                logging.warning(f'WARNING: Sentence "{sentence[0:50]}...." was too long and was skipped')
                pass
            file_name = f'{"0000000"[:-len(str(index + offset))] + str(index + offset)}'
            file_path = f'{full_path}staging/{file_name}.wav'

            with open(metadata_path, "a") as f:
                f.write(f'file {file_name}.wav\nfile {file_name}-s.wav\n')
                os.system(f'cp {full_path}audio_processing/silence.wav {full_path}staging/{file_name}-s.wav')
            self.ap.save_wav(wav=outputs['wav'], path=file_path, sr=24000)
        os.system(f'ffmpeg -y -loglevel error -f concat -i  {metadata_path} {full_path}final.mp3')
class TTSTextProcessor:
    def preprocess_text(self, input_text, rules_list):
        for rule in rules_list:
            input_text = input_text.replace(*rule)  # perform text substitutions based
        return input_text

    def split_text(self, input_text):
        split_text = re.split(r'(\. |\?|\!)', input_text)
        for index, sentence in enumerate(split_text):
            sentence = sentence.lstrip()
            if len(sentence) > 0:
                try:
                    split_text[index] += split_text[index + 1] + " "
                    split_text[index + 1] = ""
                except:
                    pass
        return list(filter(None, split_text))


"""
        This function produces an audio clip of the given text being spoken with the given reference voice.

        Args:
            text: (str) Text to be spoken.

            ref_audio_path: (str) Path to a reference audio file to be used for cloning. This audio file should be >3
                seconds long.

            language: (str) Language of the voice to be generated.

            temperature: (float) The softmax temperature of the autoregressive model. Defaults to 0.65. # too low tends to make have odd clipped silence due to lacking sylables

            length_penalty: (float) A length penalty applied to the autoregressive decoder. Higher settings causes the
                model to produce more terse outputs. Defaults to 1.0.

            repetition_penalty: (float) A penalty that prevents the autoregressive decoder from repeating itself during
                decoding. Can be used to reduce the incidence of long silences or "uhhhhhhs", etc. Defaults to 2.0.

            top_k: (int) K value used in top-k sampling. [0,inf]. Lower values mean the decoder produces more "likely"
                (aka boring) outputs. Defaults to 50.

            top_p: (float) P value used in nucleus sampling. (0,1]. Lower values mean the decoder produces more "likely"
                (aka boring) outputs. Defaults to 0.8.

            gpt_cond_len: (int) Length of the audio used for cloning. If audio is shorter, then audio length is used
                else the first `gpt_cond_len` secs is used. Defaults to 30 seconds.

            gpt_cond_chunk_len: (int) Chunk length used for cloning. It must be <= `gpt_cond_len`.
                If gpt_cond_len == gpt_cond_chunk_len, no chunking. Defaults to 6 seconds.

            hf_generate_kwargs: (**kwargs) The huggingface Transformers generate API is used for the autoregressive
                transformer. Extra keyword args fed to this function get forwarded directly to that API. Documentation
                here: https://huggingface.co/docs/transformers/internal/generation_utils

        Returns:
            Generated audio clip(s) as a torch tensor. Shape 1,S if k=1 else, (k,1,S) where S is the sample length.
            Sample rate is 24kHz.
"""

""" repetition_penalty=10"""
# conf = BaseAudioConfig(pitch_fmax=640, pitch_fmin=1)
