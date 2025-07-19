# Make shure Zabbix can run scripts as sudo. All scripts in the script folder
echo 'zabbix ALL=(ALL) NOPASSWD: /etc/zabbix/scripts/*' > /etc/sudoers.d/zabbix_scripts
chmod 440 /etc/sudoers.d/zabbix_scripts


# Make shure Zabbix can run scripts as sudo. Specific scripts in the script folder
echo 'zabbix ALL=(ALL) NOPASSWD: /etc/zabbix/scripts/listning_ports.sh' > /etc/sudoers.d/zabbix_script
chmod 440 /etc/sudoers.d/zabbix_script



vi /etc/zabbix/scripts/listning_ports.sh


chmod +x /etc/zabbix/scripts/listning_ports.sh
chown root:zabbix /etc/zabbix/scripts/listning_ports.sh

echo 'zabbix ALL=(ALL) NOPASSWD: /etc/zabbix/scripts/listning_ports.sh' > /etc/sudoers.d/zabbix_script
chmod 440 /etc/sudoers.d/zabbix_script

sed -i '$aUserParameter=service.listening.port,sudo /etc/zabbix/scripts/listning_ports.sh' /etc/zabbix/zabbix_agent2.conf

systemctl restart zabbix-agent2.service

systemctl status zabbix-agent2.service

sudo -u zabbix sudo /etc/zabbix/scripts/listning_ports.sh
