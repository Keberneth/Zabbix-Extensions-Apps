# Report Web GUI for Zabbix.
# WORKING PROGRESS. NOT DONE!
# eXTREMLEY SLOW START BECAUSE BUILDING REPORTS DURING STARTUP

## Prepare Python
## List
ls /usr/bin/python*

## Check python version assosiated with the python command
python --version

## If lover then python 3.10 change the python command
## You do not need to do this. You can just write python3.10 (or higher version) and change to that in the service file 
sudo alternatives --config python
## Select a version higher or eaqual to 3.10 

## Install pip
pip --version<br/>
pip install --upgrade pip

## Install requirements
pip install fastapi uvicorn[standard] requests openpyxl python-multipart email-validator jinja2 orjson


## Downoad the zabbix_report folder from git to
/otp/zabbix_report/

## Create the service file
vi /etc/systemd/system/zabbix-report.service

## Update environment varibles in .service
Environment="ZABBIX_API_TOKEN=/etc/zabbix_report/token"<br/>
Environment="ZABBIX_URL=https://your-zabbix-url/api_jsonrpc.php"<br/>
Environment="PYTHONUNBUFFERED=1"

# Create the token file
mkdir /etc/zabbix_report
# add the api key to the file
vi /etc/zabbix_report/token
chown root:nginx /etc/zabbix_report /etc/zabbix_report/token
chmod 0750 /etc/zabbix_report
chmod 0660 /etc/zabbix_report/token
chattr +i /etc/zabbix_report/token

## Change port if needed
--port 8081 \

## Create the nginx file
/etc/nginx/conf.d/zabbix-report.conf

## Set premissions
sudo chown -R root:root /opt/zabbix_report<br/>
sudo chmod -R 755 /opt/zabbix_report<br/>
sudo chown -R zabbix:zabbix /opt/zabbix_report/data<br/>
sudo chmod -R 750 /opt/zabbix_report/data<br/>

sudo mkdir -p /opt/zabbix_report/data
sudo mkdir -p /var/log/zabbix-report
sudo chown nginx:nginx /opt/zabbix_report/data /var/log/zabbix-report
sudo chmod 750 /opt/zabbix_report/data /var/log/zabbix-report
sudo systemctl restart zabbix-report

mkdir -p /opt/zabbix_report/backend/emailer/reports
touch /opt/zabbix_report/backend/__init__.py
touch /opt/zabbix_report/backend/emailer/__init__.py
touch /opt/zabbix_report/backend/emailer/reports/__init__.py
systemctl restart zabbix-report

## Fix logging folder and permissions
sudo mkdir -p /var/log/zabbix-report<br/>
sudo chown -R zabbix:zabbix /var/log/zabbix-report<br/>
sudo chmod 750 /var/log/zabbix-report<br/>

## Run application manually (Good for testing)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8081

## Enable service
sudo systemctl daemon-reload<br/>
sudo systemctl enable zabbix-report<br/>
sudo systemctl start zabbix-report<br/>
sudo systemctl status zabbix-report<br/>



## URLs (FQDN set in nginx conf)
https://FQDN<br/>

## Health
https://FQDN/api/status<br/>

## Report
https://FQDN/api/reports/sla<br/>
https://FQDN/api/reports/availability<br/>
https://FQDN/api/reports/icmp<br/>
https://FQDN/api/reports/host-info<br/>
https://FQDN/api/reports/utilization<br/>
https://FQDN/api/reports/firewall-if-usage<br/>
https://FQDN/api/reports/uptime-trend<br/>

## Download
https://FQDN/api/reports/sla/download<br/>
https://FQDN/api/reports/uptime-trend/download<br/>
https://FQDN/api/reports/incidents/download<br/>

## Incidents
https://FQDN/api/reports/incidents/refresh<br/>
https://FQDN/api/reports/incidents<br/>

## Email
https://FQDN/api/email/settings<br/>
https://FQDN/api/email/settings<br/>
https://FQDN/api/email/send-report<br/>
