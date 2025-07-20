This is an working early stage application with AI instructions directly in the python backend code. 
A big improvment will be to have a RAG backen to connect to documentention and websearch and provide instructions to the AI.
A AI trained on you own data will performe better to your specified needs. 


Application Requirement
Python 3.12


Create the WEB_HELP_DIR
This could be any path on the server or nginx folder. Just depends on the installation. 
For a "regular installation of Zabbix" the folder can be placed in the zabbix directory. 
WEB_HELP_DIR = "/usr/share/zabbix/ai//problems
"

sudo mkdir -p /zabbix/ai/problems /usr/share/zabbix/ai/problems

The Python service will recive the webhook from the media type from Zabbix and sent it to the AI of your choise with the included instructions and if avalible Netbox data from that host that has a triggered problem. 
Create an answere and then a html file will be created in /usr/share/zabbix/ai/problems and a URL link will be posted as a message to that active problem. 
When a resolve is sent from Zabbix that HTML file will be deleted. 

The index.html file is not needed. It's just a simple html website that will show the created html helper files from the AI and a simple way to read the log output from the python backend. 

Create the folder for the Python backend.
mkdir /opt/zabbix_ai