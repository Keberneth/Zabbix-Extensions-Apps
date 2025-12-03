Report Web GUI for Zabbix.
WORKING PROGRESS. NOT DONE!

# Prepare Python
# List
ls /usr/bin/python*

# Check python version assosiated with the python command
python --version

# If lover then python 3.10 change the python command
# You do not need to do this. You can just write python3.10 (or higher version) and change to that in the service file 
sudo alternatives --config python
# Select a version higher or eaqual to 3.10 

# Install pip
pip --version
pip install --upgrade pip

# Install requirements
pip install fastapi uvicorn[standard] requests openpyxl python-multipart email-validator jinja2 orjson


# Downoad the zabbix_report folder from git to
/otp/zabbix_report/

# Create the service file
/etc/systemd/system/zabbix-report.service

# Update environment varibles in .service
Environment="ZABBIX_API_TOKEN=/etc/zabbix_report/token"
Environment="ZABBIX_URL=https://your-zabbix-url/api_jsonrpc.php"
Environment="PYTHONUNBUFFERED=1"

# Change port if needed
--port 8081 \

# Create the nginx file
/etc/nginx/conf.d/zabbix-report.conf

# Set premissions
sudo chown -R root:root /opt/zabbix_report
sudo chmod -R 755 /opt/zabbix_report
sudo chown -R zabbix:zabbix /opt/zabbix_report/data
sudo chmod -R 750 /opt/zabbix_report/data

# Fix logging folder and permissions
sudo mkdir -p /var/log/zabbix-report
sudo chown -R zabbix:zabbix /var/log/zabbix-report
sudo chmod 750 /var/log/zabbix-report

# Run application manually (Good for testing)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8081

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable zabbix-report
sudo systemctl start zabbix-report
sudo systemctl status zabbix-report



# URLs (FQDN set in nginx conf)
https://FQDN

# Health
https://FQDN/api/status

# Report
https://FQDN/api/reports/sla
https://FQDN/api/reports/availability
https://FQDN/api/reports/icmp
https://FQDN/api/reports/host-info
https://FQDN/api/reports/utilization
https://FQDN/api/reports/firewall-if-usage
https://FQDN/api/reports/uptime-trend

# Download
https://FQDN/api/reports/sla/download
https://FQDN/api/reports/uptime-trend/download
https://FQDN/api/reports/incidents/download

# Incidents
https://FQDN/api/reports/incidents/refresh
https://FQDN/api/reports/incidents

# Email
https://FQDN/api/email/settings
https://FQDN/api/email/settings   (PUT)
https://FQDN/api/email/send-report
