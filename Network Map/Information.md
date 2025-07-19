Short Description:

Deploy Netbox and Zabbix

Import the Network map tamplates to Zabbix and add them to the hosts. 

Add the zabbix-agent conf files to the hosts and create the script folder:
Linux: /etc/zabbix/scripts/
Windows: C:\Program Files\Zabbix Agent 2\scripts\
and add the scripts here. Make shure on linux to make them executible. chmod +x /etc/zabbix/scripts/linux-network-connections.sh

network-map-report.py create a 30 days report files from all network data that exsist on the hosts item for 30 days back. (Simple solution is to create a cron job that runs the script)(See installation instructions)

The network_map application download 24 hours of network data every 30 minutes for every host. Can be changed byh modifying main.py.

The filter in the app is basically a simple source and destionation based. Ports can be added multiple by "," comma separate the ports. Port range can also be filtered by adding a range like 21-22 or 1-10000.

Netbox data is updated every 24 hours. (Can be modified in main.py code)

By clicking a host on the map you will get Netbox data and all inkomming and oputgoing connections in a "pop-up" window at the bottom of the page. Netbox link will also link to the netbox host. 
The trafik windows can be filtred by inkluding and using "!" to exclude ports or hosts, like !80,443 will exclude those ports. 

