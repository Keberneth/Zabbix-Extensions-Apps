Download the files <br/>
Save in the folder where you want to run the container<br/>

change the config.py and .env file to your URL and API
If Zabbix and NetBox run on the same host as the container, use the host’s IP/DNS:

Build image<br/>
docker compose build

Start container<br/>
docker compose up -d