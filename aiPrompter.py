# -*- coding: utf-8 -*-
import requests as requests
import urllib
import json
import sys
import socket 
import time
import subprocess
import os
import random
import logging
def processUp(procName):
    try:
        call = subprocess.check_output("pidof '{}'".format(procName), shell=True)
        return True
    except subprocess.CalledProcessError:
        return False

# ensure no conflicts.
while processUp("llama"):
	time.sleep(30)

#with open('users.json', 'w') as f:
#    json.dump(rooms, f)
room = ""
#messageSender = "kyler@upperdeckcommittee.xyz" #sys.argv[2]
json_object = {}
try:
	os.create("users.json")
except:
	pass

# Currently all requests are handled seperately.
#room = requests.post("http://localhost:8008/api/chat").text.replace("\"","")
# Code for handling persisant user rooms. Currently bugged
'''
with open('users.json', 'r+') as usersFile:
	
	try:
		json_object = json.load(usersFile)
		room = json_object[messageSender]
	except:
		response = requests.post("http://localhost:8008/api/chat").text.replace("\"","")
		#print("-------------------------" )
		rooms = {messageSender : response}
		json_object.update(rooms)
		#print(json_object)
		usersFile.truncate(0)
		json.dump(json_object,usersFile)
		# TODO find platform agnostic solution
		os.system("cat -vt users.json | tr -d '^@' > users.json")
'''


aiPrompt = sys.argv[1].encode('unicode_escape').decode()
#print(aiPrompt)
#print("Blah")
promptCommand ="profiles/assistant-oneshot.sh"

#readCommand="cat /dev/shm/log.txt"
#readCommand="cat /dev/shm/log.txt  | tail -n +6 | head -n -1 | awk -F ':' 'NR == 1 {print $2}' | awk '{$1=$1;print}'; cat /dev/shm/log.txt | tail -n +7"
readCommand="cat /dev/shm/log.txt | tail -n +8"
try:
	subprocess.run([promptCommand,aiPrompt],capture_output=False, timeout=600)
	response = subprocess.run([readCommand], shell=True, capture_output=True,timeout=600).stdout
	print(str(response,'utf-8'))
except Exception as e:
    logging.error('Caught an exception: %s', e)
    print("ERROR")
    print(e)
    
#aiPromptEncoded = urllib.parse.quote_plus(aiPrompt)
#response = requests.post("http://localhost:8008/api/chat/"+room+"/question?prompt="+aiPromptEncoded)
#responseJson = response.json()


#print("Prompt: "+ aiPrompt)
#print("Length of Prompt: "+ str(len(aiPrompt)))
#print("Chat ID: "+ room)
#print(responseJson['answer'])
#print("Length of Response: "+str(len(responseJson['answer'])))
#requests.delete("http://localhost:8008/api/chat/"+room)

# april fools joke.

llamaArt="""
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
⠀⠀⠀⠀⠀⠀⠀⠀⠛⠚⠀⢸⡇⣰⠏⠁⠀⠀⠀⠀⢉⠁⢸⠷⠼⠃⠀⠀
Thus sayeth the LLaMA
"""
if random.randint(0,255) == 254:
	print(llamaArt)
else:
	messageList = ["If the response you got did not satisfy please ask again or rephrase your question.", "Remember at this time LLaMA does not remember your previous questions.", "Did you know you can ask the AI to interpret generate, or correct code blocks", "Did you know you can ask the AI to write a short story or song lyrics with certain elements", "Did you know you can ask for the AI to interpret or modify a block of text", "The AI may misunderstand or fabricate information when answering, remember to verify received answers with trusted information sources", "Did you know the AI can have its personality changed to better suit the users, ask the admin for details"]
	print("--------------------------------------")
	print(random.choice(messageList))
	print()
