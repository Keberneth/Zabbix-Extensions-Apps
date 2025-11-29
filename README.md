Application, integrations and templates for Zabbix and Netbox. 
Using Netbox as a source of truth for virtual machines and network and use Zabbix to get more and better instight in the environment, not just monitoring. 

Templates for extending the monitoring in Zabbix and give more information, insights to Netbox and administrators. 

Network map:
Zabbix collect all established TCP connections every 5 minutes and Network map updates this every 5 minutes to get a ionteractive and up to date network map for the last 24 hours to view all established TCP connections from and to all servers that Zabbix monitor. 
When clicking on a server on the map. TCP connection information and information from Netbox will show. 

Posibility to filter map based on:
Source

Destination

Port, ports and port range


Report button to download 30 day history in:
Excel, csv and drawio files


Zabbix AI:
A simple AI integrations. Triggerred problems is sent to python backend that collect information from Zabbix using trigger action webhook and enrished the information with information about the virtual machine from Netbox. Send the information to the AI you choose to use in Ollama. 
The answer from the AI is saved as an htmlfile and link to the file is published as a messsage on the active triggered problem in Zabbix. (simple 1st line analysis). When problem is resolved the html file is removed, as long as send resolve is active in the Zabbix AI media. 

Zabbix to Netbox integration:
Is the templates are used to monitor the hosts the following information will be updated on the virtual machines in Netbox: (The virtual machines need to have the same name in Zabbix as in Netbox) 
CPU
Ram
Disks (In GB)
Services and TCP port service is listning to
# If Netbox custom Fiealds are created
Operating System
# If server running integration script can connect to endoflife.date
End Of Life date for OS
