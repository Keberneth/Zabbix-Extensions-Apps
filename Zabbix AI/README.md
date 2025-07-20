Prerequsite

1. Install python 3.12
2. Install pip
3. Install nginx (Optional)

Set up the service

1. Create the service 
vi etc/systemd/system/zabbix_ai.service
(See .service file)

2. Install pip
sudo dnf install python3-pip

sudo apt update
sudo apt install python3-pip

3. Install dependencis
pip install fastapi requests urllib3

4. Create the needed folders
(If "Regular" installation of Zabbix)
sudo mkdir -p /zabbix/ai/problems /usr/share/zabbix/ai/problems
Can be any folder path, just change it in the code if using other path. 

5. Create the folder for the python backen
mkdir /opt/zabbix_ai/

6. Create the application file (Change the API key) (Use vault encryption, do not have API key in clear text in the code)
vi /opt/zabbix_ai/zbx_ollama.py or vi /opt/zabbix_ai/zbx_gpt.py (for openai version)
(se the python backend files)

7. Reload the service deamon
sudo systemctl daemon-reload

8. Enable and start the service
sudo systemctl enable zabbix_ai
sudo systemctl start zabbix_ai

See that the service is running correctly
sudo systemctl status zabbix_ai

9. Import the Zabbix Media type, change the URL in the java script and set what severity should be sent to the AI