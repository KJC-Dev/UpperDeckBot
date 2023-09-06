#!/bin/bash
set -e

AI_NAME="${AI_NAME:-WZ7B}"
MODEL="${MODEL:-/media/mx/5CBA250DBA24E56C/mythomax-l2-13b.ggmlv3.q4_K_M.bin}"
USER_NAME="${USER_NAME:-Human}"

# Uncomment and adjust to the number of CPU cores you want to use.
N_THREAD="${N_THREAD:-6}"
N_PREDICTS="${N_PREDICTS:-4096}"

GEN_OPTIONS=(--batch_size 256
--ctx_size 2048
--keep -1
--repeat_last_n 256
--repeat_penalty 1.2
--temp 0.7
--top_k 80
--top_p 0.5
--n-gpu-layers 999
--mirostat 2)


function fileAge
{
    local fileMod
    if fileMod=$(stat -c %Y -- "$1")
    then
        echo $(( $(date +%s) - $fileMod ))
    else
        return $?
    fi
}


function killCheck
{	
	sleep 60
	until [ $(grep -c "Instruction:" /dev/shm/log.txt) -ge 2 ] || [ $(fileAge /dev/shm/log.txt) -ge 10 ]; do
		sleep 3
	done
	killall llama
}	
killCheck &

if [ -n "$N_THREAD" ]; then
	GEN_OPTIONS+=(--threads "$N_THREAD")
fi

./llama "${GEN_OPTIONS[@]}" \
	--model "$MODEL" \
	--n_predict "$N_PREDICTS" \
	--prompt "
Below is an instruction that describes a task. Write a response that appropriately completes the request.

### Instruction:
$@
### Response:" > /dev/shm/log.txt 2>/dev/null
