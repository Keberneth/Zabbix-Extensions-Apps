# Create a docker folder. I have created it directly under root 
mkdir /docker

# 1. generate one new NetBox secret (≥ 50 chars) and paste into the file docker-compose-zbx_nbox.yml
python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'

# Or spin up the container, login to it and generate the key
docker compose -f docker-compose-zbx_nbox.yml exec netbox /bin/bash

  python3 /opt/netbox/netbox/generate_secret_key.py

# 2. bring everything up
docker compose -f docker-compose-zbx_nbox.yml up -d

# 3. initial NetBox DB & admin user
    # Do a migration of Netbox
docker compose -f docker-compose-zbx_nbox.yml exec netbox /bin/bash

  python3 /opt/netbox/netbox/manage.py migrate

    # Create an admin user
docker compose -f docker-compose-zbx_nbox.yml exec netbox /bin/bash
  python3 /opt/netbox/netbox/manage.py createsuperuser


--------------------------------------------------------------------------------------


cd /docker               # directory that holds the compose file

docker compose \
  -f docker-compose-zbx_nbox.yml \
  up -d --pull always --force-recreate \
  zabbix-server zabbix-web netbox


pulls newer images for the three services you listed;

recreates zabbix‑server, zabbix‑web, and netbox containers;

automatically (re)starts any services they depends_on (Postgres, Redis, agent, …);

leaves everything else untouched.

--------------------------------------------------------------------------------------

If you want every service in the file, omit the service names entirely:
cd /docker               # directory that holds the compose file

docker compose \
  -f docker-compose-zbx_nbox.yml \
  up -d --pull always --force-recreate \
  zabbix-server zabbix-web netbox
