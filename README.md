# Linux service for Zabbix Network Map and integration script from Zabbix to Netbox. 
Using Netbox as a source of truth for virtual machines and network and use Zabbix to get more and better instight in the environment, not just monitoring.


Templates for extending the monitoring in Zabbix and give more information, insights to Netbox and administrators. 


## **Network map**

Zabbix collect all established TCP connections every 5 minutes and Network map updates this every 5 minutes to get a ionteractive and up to date network map for the last 24 hours to view all established TCP connections from and to all servers that Zabbix monitor. 
When clicking on a server on the map. TCP connection information and information from Netbox will show. 

Posibility to filter map based on:<br>
Source<br>
Destination<br>
Port, ports and port range<br><br>


Report button to download 30 day history in:<br>
Excel, csv and drawio files<br><br>


## **Zabbix to Netbox integration**

Is the templates are used to monitor the hosts the following information will be updated on the virtual machines in Netbox: (The virtual machines need to have the same name in Zabbix as in Netbox) 
CPU<br>
Ram<br>
Disks (In GB)<br>
Services and TCP port service is listning to<br>
**If Netbox custom Fiealds are created**<br>
Operating System<br>
**If server running integration script can connect to <u>endoflife.date</u>**<br>
End Of Life date for OS<br>
