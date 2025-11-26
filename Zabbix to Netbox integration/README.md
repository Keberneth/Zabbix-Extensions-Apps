The script will update the following on Netbox Virtual Machines if the hostname is the same in Zabbix as ini Netbox.
CPU
RAM
Disks
Service with listning TCP port

If Virtual Machine custom fields are created:
Operating System
End of life date

To make the OS update and EOL date to be published on the virtual machine in Netbox the following custom fields need to be created in Netbox on Virtual Machines.

operating_system
operating_system_EOL

and the host running the script need to be able to access the website endoflife.date

Run the integration script with a cronjob as often as you want.

To make the Linux OS update and EOL work the template "Linux Monitoring Zabbix Agent Active" need to be used. The discovery for OS PRETTY NAME is needed.

For Listning port services to be updated on Virtual Machines in Netbox, Zabbix template "Windows Service Listning Port Zabbix Agent Active" and Linux Service Listning Port Zabbix Agent Active" need to be used.
They have a conf file and script that need to be added to the servers. 


Script also send error to zabbix if it fails. Use a Zabbix trapper tempalte with the key and host name in the script and change to the correct IP.

For this to work Zabbix Sender needs to be installed on the host running the scripts and template "Zabbix to Netbox Script Trapper" needs to be on the server reciving send

# Configure these to match your Zabbix setup
ZABBIX_SENDER = os.getenv("ZABBIX_SENDER", "/usr/bin/zabbix_sender")
ZABBIX_SERVER = os.getenv("ZABBIX_SERVER", "127.0.0.1")          # Zabbix server address
ZABBIX_HOST   = os.getenv("ZABBIX_HOST", "netbox-sync-host")     # Host name in Zabbix
ZABBIX_KEY    = os.getenv("ZABBIX_KEY", "netbox.sync.status")    # Trapper item key
