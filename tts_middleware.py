import logging
import random

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
                     ["TV", "television"],
                     ["PC", "personal computer"],
                     [" -", ", "],
                     ["*",""],
                     ["^",""]]


class TTSAudioController:
    # device = "cpu"
    # List available 🐸TTS models
    # print(TTS().list_models())
    # Init TTS
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.config = XttsConfig()
        self.config.load_json(full_path + "XTTS-v2/config.json")
        self.model = Xtts.init_from_config(self.config)
        self.model.load_checkpoint(self.config, checkpoint_dir=full_path + "XTTS-v2/", eval=True)
        self.model.cuda()
        self.conf = BaseAudioConfig(pitch_fmax=None, pitch_fmin=None)
        self.ap = TTS.TTS.utils.audio.AudioProcessor(**self.conf)

    def run_model(self, sentences:list, speakers:list ):
        for speaker in speakers:
            if not os.path.exists(speaker):
                raise FileNotFoundError(f'Path to speaker {speaker} not found.')
                exit(1)
        os.system("cp " + full_path + "audio_processing/basefile.wav " + full_path + "final.wav")
        for sentence in sentences:
            outputs = self.model.synthesize(text=sentence,
                                            config=self.config,
                                            speaker_wav=speakers,
                                            language="en",
                                            top_k=50,
                                            top_p=0.7,
                                            temperature=0.75,
                                            repetition_penalty=2.0,
                                            do_sample=True,
                                            gpt_cond_len=9999)

            self.ap.save_wav(path=full_path + "output.wav",wav=outputs['wav'],sr=24000)
            os.system("ffmpeg -y  -loglevel error  "
                      "-i " + full_path + "final.wav "
                                          "-i " + full_path + "output.wav "
                                                              "-filter_complex [0:a][1:a]concat=n=2:v=0:a=1 "
                      + full_path + "appended_final.wav")
            os.system(f'ffmpeg -y -loglevel error -i  {full_path}appended_final.wav -i {full_path}audio_processing'
                      f'/silence.wav -filter_complex [0:a][1:a]concat=n=2:v=0:a=1 {full_path}final.wav')
            os.system(f'ffmpeg -i {full_path}final.wav -i '
                      f'{full_path}audio_processing/brown-noise.wav '
                      f'-filter_complex '
                      f'amix=inputs=2:duration=shortest '
                      f'{full_path}output.mp3 -y')
        try:
            os.remove(f'{full_path}final.wav')
            os.remove(f'{full_path}appended_final.wav')
            os.remove(f'{full_path}output.wav')
        except:
            logging.warning("File was not removed correctly")


class TTSTextProcessor:
    def preprocess_text(self, input_text, rules_list):
        for rule in rules_list:
            input_text = input_text.replace(*rule) # perform text substitutions based on t
        return input_text

    def split_text(self, input_text):
        split_text = re.split(r'(\. |\?|\!)', input_text)
        for index, sentence in enumerate(split_text):
            if len(sentence) > 0:
                try:
                    split_text[index]+= split_text[index + 1]+" "
                    split_text[index+1] = ""
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
