#!/bin/bash
set -e

AI_NAME="${AI_NAME:-WZ13B}"
MODEL="${MODEL:-./models/wizardLM-7B.ggmlv3.q4_1.bin}"
USER_NAME="${USER_NAME:-Human}"

# Uncomment and adjust to the number of CPU cores you want to use.
N_THREAD="${N_THREAD:-12}"
N_PREDICTS="${N_PREDICTS:-4096}"

GEN_OPTIONS=(--batch_size 1024
--ctx_size 2048
--keep -1
--repeat_last_n 256
--repeat_penalty 1.17647
--temp 0.7
--top_k 40
--top_p 0.5)

if [ -n "$N_THREAD" ]; then
	GEN_OPTIONS+=(--threads "$N_THREAD")
fi

./llama "${GEN_OPTIONS[@]}" \
	--model "$MODEL" \
	--n_predict "$N_PREDICTS" \
	--color --interactive \
	--reverse-prompt "${USER_NAME}:" \
	--instruct
	--prompt "
### Human: Hello, Assistant.
### Assistant: Hello. How may I help you today?
### Human: Please tell me the largest city in Europe.
### Assistant: Sure. The largest city in Europe is Moscow, the capital of Russia.
### Human:" "$@"
